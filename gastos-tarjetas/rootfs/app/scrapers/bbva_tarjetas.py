"""
Scraper BBVA Argentina — Tarjetas de Crédito (Visa y Mastercard).

Misma estrategia que el scraper de cuentas (bbva.py): hereda BbvaScraper
para login / sesión / _api_request y solo overridea scrape().

Flujo (confirmado por HAR bbvalogin6.har):
  1. GET  /cliente/productos/tarjetas
       → lista tarjetasCreditoVisa / tarjetasCreditoMastercard
       → cada item tiene `id` (numérico) y `numeroPan` (token opaco)
  2. GET  /cards/v1/cards/{numeroPan}/transactions
       → array `data[]` con los consumos del período en curso
       → campos: localAmount.{amount,currency}, concept, operationDate
  3. GET  /cliente/productos/tarjetas/{id}/datosultimoproximoresumen
       → result.estadoActual.{saldoPesos, saldoDolares}

Tarjetas soportadas:
  tarjetasCreditoVisa        → fuente "bbva_visa"
  tarjetasCreditoMastercard  → fuente "bbva_mc"

El mapeo tarjeta→fuente se puede overridear vía __cuentas__ del scheduler
usando product_key="VISA" o product_key="MC".
"""

import logging
import re
from typing import Optional

from .base import MovimientoRaw, ScraperResult
from .bbva import BbvaScraper

logger = logging.getLogger(__name__)

_FUENTE_VISA = "bbva_visa"
_FUENTE_MC   = "bbva_mc"

_EP_TARJETAS   = "/cliente/productos/tarjetas"
_EP_TRANSACC   = "/cards/v1/cards/{pan}/transactions"
_EP_RESUMEN    = "/cliente/productos/tarjetas/{id}/datosultimoproximoresumen"

# Detecta tipo de tarjeta por nombre de clave en la API
_VISA_RE = re.compile(r"\bvisa\b",        re.IGNORECASE)
_MC_RE   = re.compile(r"\bmastercard\b",  re.IGNORECASE)

# Tipos de transacción que son pagos/créditos (monto negativo)
_CREDITO_TYPES = {"PAYMENT", "CREDIT", "PAGO", "CREDITO", "REFUND", "REVERSAL"}


class BbvaTarjetasScraper(BbvaScraper):
    fuente = "bbva_tarjetas"
    nombre = "BBVA Argentina — Tarjetas de Crédito"

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva-tj] %s", msg)
            log.append(msg)

        # Resolver fuentes (defaults + override por __cuentas__)
        product_to_fuente: dict[str, str] = {"VISA": _FUENTE_VISA, "MC": _FUENTE_MC}
        cuentas_map = config.get("__cuentas__") or []
        if cuentas_map:
            for c in cuentas_map:
                pk = (c.get("product_key") or "").upper()
                if pk and c.get("fuente"):
                    product_to_fuente[pk] = c["fuente"]
            _log(f"Modo multi-instancia — mapeo final: {product_to_fuente}")
        else:
            _log(f"Modo default — mapeo: {product_to_fuente}")

        usuario_default = (config.get("usuario_default") or "").strip() or None

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # ── 1. Lista de tarjetas ──────────────────────────────────────────────
        resp = self._api_request(driver, _EP_TARJETAS)
        _log(f"GET {_EP_TARJETAS} → HTTP {resp['status']}")
        if resp["status"] != 200 or not resp["json"]:
            _log("⚠ No se pudo obtener la lista de tarjetas")
            return ScraperResult(fuente=self.fuente, movimientos=[], log_lines=log)

        tarjetas = self._extract_tarjetas(resp["json"], _log)
        _log(f"Tarjetas encontradas: {len(tarjetas)}")

        # ── 2. Consumos + saldo por tarjeta ───────────────────────────────────
        for tj in tarjetas:
            tipo   = tj["tipo"]
            nombre = tj["nombre"]
            fuente = product_to_fuente.get(tipo)
            if not fuente:
                _log(f"  Saltando {nombre} (tipo={tipo} sin mapeo)")
                continue

            _log(f"  Procesando {nombre} → fuente={fuente}")
            try:
                movs, saldo = self._fetch_tarjeta(driver, tj, fuente, usuario_default, _log)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos[fuente] = {"saldo_ars": saldo}
                _log(f"  → {len(movs)} consumos, saldo={saldo}")
            except Exception as exc:
                _log(f"  ✗ Error en {nombre}: {exc}")
                logger.exception("[bbva-tj] Error scrapeando %s", nombre)

        return ScraperResult(
            fuente      = self.fuente,
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    # ── Extracción de tarjetas del JSON ──────────────────────────────────────

    def _extract_tarjetas(self, json_body: dict, log_fn) -> list[dict]:
        """
        Parsea GET /cliente/productos/tarjetas.
        Itera sobre las claves del result que contengan "credito" en el nombre
        (tarjetasCreditoVisa, tarjetasCreditoMastercard) y deduce el tipo
        (VISA / MC) del nombre de la clave.
        Extrae id, numeroPan y nombre de cada item.
        """
        result = json_body.get("result") or json_body
        if not isinstance(result, dict):
            log_fn(f"  [diag] result inesperado: {str(json_body)[:300]}")
            return []

        tarjetas = []
        for key, items in result.items():
            if not isinstance(items, list) or not items:
                continue
            kl = key.lower()
            if "debito" in kl or "debit" in kl:
                continue  # ignorar tarjetas de débito
            if "credito" not in kl and "credit" not in kl and "card" not in kl:
                continue

            tipo = "VISA" if _VISA_RE.search(key) else ("MC" if _MC_RE.search(key) else None)
            log_fn(f"  Clave '{key}': {len(items)} items (tipo={tipo})")

            for item in items:
                id_tj     = str(item.get("id") or item.get("idProducto") or "")
                numero_pan = str(item.get("numeroPan") or "")
                numero    = item.get("numero") or ""

                if not id_tj or not numero_pan:
                    log_fn(f"  ⚠ Item sin id o numeroPan: {item}")
                    continue

                # Tipo desde la clave; fallback por campos del item
                t = tipo
                if t is None:
                    texto = " ".join(str(item.get(k) or "") for k in
                                     ("alias", "descripcion", "marca", "brand"))
                    t_sub = item.get("tipoProducto") or {}
                    texto += " " + str(t_sub.get("descripcion") or "")
                    if _VISA_RE.search(texto):   t = "VISA"
                    elif _MC_RE.search(texto):   t = "MC"
                    else:
                        log_fn(f"  Tipo no reconocido: {str(item)[:200]}")
                        continue

                nombre = (
                    item.get("alias") or
                    (item.get("tipoProducto") or {}).get("descripcion") or
                    ("Visa" if t == "VISA" else "Mastercard")
                )

                tarjetas.append({
                    "id":        id_tj,
                    "pan":       numero_pan,
                    "tipo":      t,
                    "nombre":    f"{nombre} {numero}".strip()[:80],
                })
                log_fn(f"  Tarjeta: tipo={t} nombre={nombre!r} num={numero} id={id_tj}")

        return tarjetas

    # ── Fetch de una tarjeta: saldo + consumos ────────────────────────────────

    def _fetch_tarjeta(
        self,
        driver,
        tj: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:

        id_tj = tj["id"]
        pan   = tj["pan"]

        # Saldo actual
        saldo = self._fetch_saldo(driver, id_tj, log_fn)

        # Consumos del período
        ep = _EP_TRANSACC.format(pan=pan)
        resp = self._api_request(driver, ep)
        log_fn(f"  GET {ep} → HTTP {resp['status']}")

        if resp["status"] != 200 or not resp["json"]:
            log_fn(f"  ⚠ Sin respuesta válida — body: {resp['body'][:300]}")
            return [], saldo

        movs = self._parse_transactions(
            resp["json"], fuente, usuario_default, log_fn, tj["nombre"]
        )
        return movs, saldo

    def _fetch_saldo(self, driver, id_tj: str, log_fn) -> Optional[float]:
        ep   = _EP_RESUMEN.format(id=id_tj)
        resp = self._api_request(driver, ep)
        log_fn(f"  GET {ep} → HTTP {resp['status']}")
        if resp["status"] != 200 or not resp["json"]:
            return None
        try:
            estado = (resp["json"].get("result") or {}).get("estadoActual") or {}
            s = estado.get("saldoPesos") or estado.get("saldoDolares")
            if s:
                val = float(str(s).replace(",", "."))
                log_fn(f"  Saldo ARS: {val}")
                return val
        except (ValueError, TypeError):
            pass
        return None

    # ── Parseo de transacciones ───────────────────────────────────────────────

    def _parse_transactions(
        self,
        json_body: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
        nombre_tarjeta: str,
    ) -> list[MovimientoRaw]:
        """
        Parsea la respuesta de GET /cards/v1/cards/{pan}/transactions.

        Estructura (confirmada por HAR):
          {
            "data": [
              {
                "localAmount":   {"amount": "5089.98", "currency": "ARS"},
                "concept":       "CONSUMO EN PESOS",
                "operationDate": "2026-06-03T00:00:00.000-0300",
                "transactionType": {"id": "AUTHORIZED", ...},
                "status":        {"id": "SETTLED", ...},
                ...
              }, ...
            ]
          }

        Convención de monto: positivo = egreso (cargo), negativo = crédito.
        Los consumos tipo "AUTHORIZED"/"SETTLED" son egresos; pagos/créditos
        se detectan por transactionType.id.
        """
        items = json_body.get("data") or []
        if not items:
            log_fn(f"  [diag] Sin items en 'data'. Keys: {list(json_body.keys())}")
            return []

        log_fn(f"  Transacciones en respuesta: {len(items)}")

        movimientos = []
        for item in items:
            mov = self._parse_one(item, fuente, usuario_default, nombre_tarjeta)
            if mov:
                movimientos.append(mov)

        return movimientos

    def _parse_one(
        self,
        item: dict,
        fuente: str,
        usuario_default: Optional[str],
        nombre_tarjeta: str,
    ) -> Optional[MovimientoRaw]:

        # Fecha — "2026-06-03T00:00:00.000-0300"
        fecha_raw = (
            item.get("operationDate") or
            item.get("accountedDate") or
            item.get("valuationDate") or ""
        )
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(fecha_raw))
        if not m:
            return None
        fecha_iso = m.group(1)

        # Descripción
        desc = (item.get("concept") or "").strip()
        if not desc:
            return None

        # Monto y moneda
        local = item.get("localAmount") or {}
        try:
            monto = float(str(local.get("amount") or 0).replace(",", "."))
        except (ValueError, TypeError):
            return None
        if monto == 0:
            return None

        moneda = "USD" if "USD" in str(local.get("currency") or "").upper() else "ARS"

        # Signo: créditos/pagos → monto negativo
        tx_type = str((item.get("transactionType") or {}).get("id") or "").upper()
        if tx_type in _CREDITO_TYPES:
            monto = -abs(monto)
        else:
            monto = abs(monto)

        raw_data: dict = {"tarjeta": nombre_tarjeta, "tx_type": tx_type}
        if usuario_default:
            raw_data["usuario"] = usuario_default
        status = (item.get("status") or {}).get("id")
        if status:
            raw_data["status"] = status

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha_iso,
            descripcion = desc[:200],
            monto       = monto,
            moneda      = moneda,
            raw_data    = raw_data,
        )

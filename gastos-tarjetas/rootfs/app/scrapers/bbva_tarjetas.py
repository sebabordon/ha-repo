"""
Scraper BBVA Argentina — Tarjetas de Crédito (Visa y Mastercard).

Misma estrategia que el scraper de cuentas (bbva.py): login natural con
Selenium + llamadas REST vía fetch() desde dentro del browser (para que
Akamai BotManager acepte las requests con el fingerprint correcto).

Hereda de BbvaScraper todo el flujo de login / sesión / _api_request.
Solo overridea scrape() para llamar los endpoints de tarjetas en lugar
de los de cuentas.

Tarjetas soportadas:
  VISA (cualquier variante)  → fuente "bbva_visa"
  MASTERCARD (Black, Gold…)  → fuente "bbva_mc"

El mapeo tarjeta→fuente se puede overridear vía __cuentas__ del scheduler
usando product_key="VISA" o product_key="MC".

Período: BBVA sólo expone los consumos del período en curso en el endpoint
de movimientos de tarjeta — el scraper importa todo lo que devuelve la API.
"""

import logging
import os
import re
from typing import Optional

from .base import MovimientoRaw, ScraperResult
from .bbva import BbvaScraper

logger = logging.getLogger(__name__)

# Fuentes por defecto cuando no hay __cuentas__ override
_FUENTE_VISA = "bbva_visa"
_FUENTE_MC   = "bbva_mc"

# Detecta tipo de tarjeta por texto de la API (marca, descripción, alias)
_VISA_RE = re.compile(r"\bvisa\b", re.IGNORECASE)
_MC_RE   = re.compile(r"\bmastercard\b|\bmaster\b", re.IGNORECASE)

# Endpoints (se ajustan con el diagnóstico del primer run)
_EP_TARJETAS  = "/cliente/productos/tarjetas"
_EP_CONSUMOS  = "/cliente/productos/tarjetas/movimientos"


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

        # ── 1. Obtener lista de tarjetas ──────────────────────────────────────
        resp = self._api_request(driver, _EP_TARJETAS)
        _log(f"GET {_EP_TARJETAS} → HTTP {resp['status']}")
        _log(f"[diag] body[:1000]: {resp['body'][:1000]}")

        if resp["status"] != 200 or not resp["json"]:
            _log("⚠ No se pudo obtener la lista de tarjetas — revisar endpoint")
            return ScraperResult(fuente=self.fuente, movimientos=[], log_lines=log)

        tarjetas = self._extract_tarjetas(resp["json"], _log)
        _log(f"Tarjetas encontradas: {len(tarjetas)}")

        # ── 2. Para cada tarjeta, obtener consumos ────────────────────────────
        for tj in tarjetas:
            tipo   = tj["tipo"]    # "VISA" o "MC"
            nombre = tj["nombre"]
            id_tj  = tj["id"]
            fuente = product_to_fuente.get(tipo)

            if not fuente:
                _log(f"  Saltando {nombre} (tipo={tipo} sin mapeo)")
                continue

            _log(f"  Procesando {nombre} (id={id_tj}) → fuente={fuente}")

            try:
                movs, saldo = self._fetch_consumos(driver, tj, fuente, usuario_default, _log)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos[fuente] = {"saldo_ars": saldo}
                _log(f"  → {len(movs)} consumos, saldo={saldo}")
            except Exception as exc:
                _log(f"  ✗ Error en {nombre}: {exc}")
                logger.exception("[bbva-tj] Error scrapeando tarjeta %s", nombre)

        return ScraperResult(
            fuente      = self.fuente,
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    # ── Extracción de tarjetas del JSON ──────────────────────────────────────

    def _extract_tarjetas(self, json_body: dict, log_fn) -> list[dict]:
        """
        Parsea la respuesta de GET /cliente/productos/tarjetas.

        BBVA devuelve las tarjetas en listas separadas por tipo bajo result:
          "tarjetasCreditoVisa":       [...] → tipo VISA
          "tarjetasCreditoMastercard": [...] → tipo MC
          "tarjetasCreditoAmex":       [...] → (ignoradas, usa scraper amex)

        El tipo se deduce del nombre de la clave; si no matchea, se intenta
        por el texto de los campos del item.
        """
        result = json_body.get("result") or json_body
        if not isinstance(result, dict):
            log_fn(f"  [diag] result no es dict: {str(json_body)[:500]}")
            return []

        # Determinar tipo por nombre de clave
        def _tipo_from_key(key: str) -> Optional[str]:
            k = key.lower()
            if "visa" in k:
                return "VISA"
            if "master" in k:
                return "MC"
            return None

        tarjetas = []
        for key, items in result.items():
            if not isinstance(items, list) or not items:
                continue

            tipo_key = _tipo_from_key(key)
            if tipo_key is None and not any(
                k in key.lower() for k in ("tarjeta", "credito", "credit", "card")
            ):
                continue  # no parece una lista de tarjetas

            log_fn(f"  Clave '{key}': {len(items)} items (tipo_key={tipo_key})")

            for item in items:
                id_tj = (
                    item.get("id") or item.get("idProducto") or
                    item.get("contractId") or item.get("contrato") or ""
                )

                # Tipo: desde la clave o desde los campos del item
                tipo = tipo_key
                if tipo is None:
                    texto = " ".join(str(item.get(k) or "") for k in (
                        "alias", "descripcion", "description",
                        "marca", "brand", "tipo", "type",
                        "tipoProducto",
                    ))
                    # También buscar en tipoProducto anidado
                    tp = item.get("tipoProducto") or {}
                    if isinstance(tp, dict):
                        texto += " " + str(tp.get("descripcion") or "")
                    if _VISA_RE.search(texto):
                        tipo = "VISA"
                    elif _MC_RE.search(texto):
                        tipo = "MC"
                    else:
                        log_fn(f"  Tipo no reconocido para item id={id_tj}: {str(item)[:200]}")
                        continue

                nombre = (
                    item.get("alias") or
                    (item.get("tipoProducto") or {}).get("descripcion") or
                    item.get("descripcion") or
                    ("Tarjeta Visa" if tipo == "VISA" else "Tarjeta Mastercard")
                )
                numero = item.get("numero") or ""

                tarjetas.append({
                    "id":     str(id_tj),
                    "tipo":   tipo,
                    "nombre": f"{nombre} {numero}".strip()[:80],
                    "raw":    item,
                })
                log_fn(f"  Tarjeta: tipo={tipo} nombre={nombre!r} numero={numero} id={id_tj}")

        return tarjetas

    # ── Consumos de una tarjeta ───────────────────────────────────────────────

    def _fetch_consumos(
        self,
        driver,
        tj: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:
        """
        Llama al endpoint de consumos de la tarjeta y parsea los movimientos.

        El cuerpo del POST se calibra con el primer run: el log diagnóstico
        muestra qué campos devuelve la API para que podamos ajustar.
        """
        id_tj = tj["id"]

        # Payload tentativo — ajustar con lo que muestre el [diag] del primer run
        payload = {
            "idProducto": id_tj,
        }

        resp = self._api_request(driver, _EP_CONSUMOS, method="POST", json_body=payload)
        log_fn(f"  POST {_EP_CONSUMOS} (id={id_tj}) → HTTP {resp['status']}")
        log_fn(f"  [diag] body[:2000]: {resp['body'][:2000]}")

        if resp["status"] != 200 or not resp["json"]:
            log_fn(f"  ⚠ Sin respuesta válida — revisar endpoint y payload")
            return [], None

        return self._parse_consumos(resp["json"], fuente, usuario_default, log_fn, tj["nombre"])

    def _parse_consumos(
        self,
        json_body: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
        nombre_tarjeta: str,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:
        """
        Convierte la respuesta JSON de consumos en MovimientoRaw.
        Soporta los formatos más comunes de la API BBVA.
        """
        result = json_body.get("result") or json_body

        # Buscar la lista de consumos bajo distintas claves
        consumos = []
        for key in ("consumos", "movimientos", "transactions", "movements",
                    "items", "data", "detalle"):
            v = result.get(key) if isinstance(result, dict) else None
            if isinstance(v, list) and v:
                log_fn(f"  Consumos en campo '{key}': {len(v)} items")
                consumos = v
                break

        if not consumos and isinstance(result, list):
            consumos = result

        if not consumos:
            log_fn(f"  [diag] JSON completo: {str(json_body)[:2000]}")
            return [], None

        log_fn(f"  [diag] Keys del primer consumo: {sorted(consumos[0].keys()) if consumos else []}")

        # Saldo total a pagar (si viene en el result)
        saldo = None
        for saldo_key in ("saldoActual", "saldo", "balance", "totalAPagar",
                          "importeTotal", "montoCierre"):
            sv = result.get(saldo_key) if isinstance(result, dict) else None
            if sv is not None:
                try:
                    saldo = float(str(sv).replace(",", "."))
                    log_fn(f"  Saldo desde '{saldo_key}': {saldo}")
                    break
                except (ValueError, TypeError):
                    pass

        movimientos = []
        for item in consumos:
            mov = self._parse_consumo(item, fuente, usuario_default, nombre_tarjeta)
            if mov:
                movimientos.append(mov)

        return movimientos, saldo

    def _parse_consumo(
        self,
        item: dict,
        fuente: str,
        usuario_default: Optional[str],
        nombre_tarjeta: str,
    ) -> Optional[MovimientoRaw]:
        """
        Parsea un consumo individual de la API BBVA.

        Convención de monto (igual que todos los parsers CC):
          monto > 0 = egreso (cargo en la tarjeta)
          monto < 0 = ingreso (crédito / devolución)
        """
        # Fecha
        fecha_raw = (
            item.get("fecha") or item.get("date") or
            item.get("fechaConsumo") or item.get("fechaMovimiento") or
            item.get("transactionDate") or ""
        )
        fecha_iso = self.parse_date_ar(str(fecha_raw))
        if not fecha_iso:
            # Intentar ISO directo (YYYY-MM-DD o YYYY-MM-DDThh:mm:ss)
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(fecha_raw))
            if m:
                fecha_iso = m.group(1)
        if not fecha_iso:
            return None

        # Descripción
        desc = (
            item.get("descripcion") or item.get("description") or
            item.get("concepto") or item.get("concept") or
            item.get("comercio") or item.get("merchant") or
            item.get("nombre") or ""
        ).strip()
        if not desc:
            return None

        # Importe
        importe_raw = (
            item.get("importe") or item.get("amount") or
            item.get("monto") or item.get("total") or
            item.get("importePesos") or 0
        )
        try:
            monto = float(str(importe_raw).replace(",", "."))
        except (ValueError, TypeError):
            return None

        if monto == 0:
            return None

        # Moneda
        moneda_raw = (
            item.get("moneda") or item.get("currency") or
            item.get("codigoMoneda") or "ARS"
        )
        moneda = "USD" if "USD" in str(moneda_raw).upper() else "ARS"

        raw_data: dict = {"tarjeta": nombre_tarjeta}
        if usuario_default:
            raw_data["usuario"] = usuario_default
        for k in ("cuotas", "numeroCupon", "codigoAutorizacion", "canal"):
            if item.get(k):
                raw_data[k] = item[k]

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha_iso,
            descripcion = desc[:200],
            monto       = monto,
            moneda      = moneda,
            raw_data    = raw_data,
        )

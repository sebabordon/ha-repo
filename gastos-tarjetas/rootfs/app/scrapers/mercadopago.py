"""
Scraper MercadoPago Argentina — API REST.

No usa Selenium. Lee los movimientos de la cuenta usando el API oficial
de MercadoPago con el Access Token personal del usuario.

Cómo obtener el Access Token:
  1. Ir a https://www.mercadopago.com.ar/developers/panel
  2. Crear (o abrir) una aplicación
  3. Producción → Credenciales de producción → Access Token
  4. Pegarlo en la UI del add-on: Config → Scrapers → MercadoPago

El token se envía como:  Authorization: Bearer {access_token}

Endpoints usados:
  GET /users/me                          → ID y datos del usuario autenticado
  GET /v1/payments/search?payer.id=…    → pagos realizados (egresos)
  GET /v1/payments/search?collector.id=… → cobros recibidos (ingresos)
  GET /v1/account/balance               → saldo disponible

Pagos con tarjeta de crédito (payment_type_id == "credit_card"):
  Se EXCLUYEN. Esos cargos aparecen en el resumen de la tarjeta (AMEX, BBVA,
  Galicia, etc.) y se importan vía PDF. Importarlos también desde MP sería
  un duplicado. Solo se importan pagos desde billetera (account_money),
  débito, transferencias, QR, etc.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from .base import BaseScraper, MovimientoRaw, ScraperResult
from scrapers_db import upsert_scraper_status

logger = logging.getLogger(__name__)

_BASE         = "https://api.mercadopago.com"
_DIAS_DEFAULT = 60    # días hacia atrás a consultar si no se configura otro valor
_PAGE_SIZE    = 50    # máximo que acepta la API

# Argentina no tiene horario de verano → UTC-3 fijo
_ART = timezone(timedelta(hours=-3))

# Códigos técnicos que puede devolver la API en reason/description; los filtramos
# para no usarlos como nombre del comercio.
_TECHNICAL_CODES = frozenset({
    "debit_card", "credit_card", "prepaid_card", "account_money", "ticket",
    "bank_transfer", "atm", "checkout_on", "checkout_pro", "regular_payment",
    "money_transfer", "money_outflows", "pos_payment", "partition_transfer",
})


class MercadoPagoScraper(BaseScraper):
    fuente       = "mercadopago"
    nombre       = "MercadoPago"
    login_origin = "https://www.mercadopago.com.ar"

    # ── Punto de entrada (override: no usa Selenium) ──────────────────────────

    async def run(self, config: dict) -> ScraperResult:
        """Implementación vía API REST. No invoca el pipeline de Selenium."""
        now_iso = datetime.utcnow().isoformat()
        upsert_scraper_status(self.fuente, estado="running", ultimo_run=now_iso)
        log: list[str] = []

        def _l(msg: str) -> None:
            logger.info("[mp] %s", msg)
            log.append(msg)

        access_token = (config.get("access_token") or "").strip()
        if not access_token:
            err = "No hay access_token configurado para MercadoPago."
            upsert_scraper_status(self.fuente, estado="error", error_msg=err)
            return ScraperResult(fuente=self.fuente, error=err, log_lines=log)

        # Usuario default para etiquetar gastos importados
        self._default_usuario = (config.get("usuario") or "").strip()

        debug_log = bool(config.get("debug_log"))

        dias = int(config.get("dias") or _DIAS_DEFAULT)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30) as client:

                # 1. Identificar al usuario
                _l("Consultando /users/me …")
                resp = await client.get(f"{_BASE}/users/me")
                resp.raise_for_status()
                user_data = resp.json()
                user_id   = user_data["id"]
                _l(f"Usuario: {user_data.get('nickname', '?')} (id={user_id})")

                # 2. Obtener IDs de pagos ya presentes en la DB (para dedup)
                existing_ids = _get_existing_payment_ids(dias)
                _l(f"Payment IDs ya conocidos en DB: {len(existing_ids)}")

                # 3. Egresos e ingresos
                movimientos, stats = await self._fetch_all(
                    client, user_id, dias, existing_ids, _l, debug_log
                )
                _l(
                    f"Nuevos: {stats['egresos']} egresos, "
                    f"{stats['ingresos']} ingresos "
                    f"({stats['skipped']} ya existían)"
                )

                # 4. Saldo
                saldos = await self._fetch_balance(client, _l)

            result = ScraperResult(
                fuente      = self.fuente,
                movimientos = movimientos,
                saldos      = saldos,
                log_lines   = log,
            )
            upsert_scraper_status(
                self.fuente,
                estado             = "ok",
                ultimo_ok          = now_iso,
                error_msg          = None,
                movimientos_nuevos = len(movimientos),
                saldo_ars          = saldos.get("mercadopago", {}).get("saldo_ars"),
                last_log           = "\n".join(log),
            )
            return result

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            body = exc.response.text[:300]
            if code == 401:
                err = "Access Token inválido o expirado (401). Regeneralo en el panel de desarrolladores de MP."
            else:
                err = f"Error HTTP {code}: {body}"
            _l(f"ERROR: {err}")
            upsert_scraper_status(
                self.fuente, estado="error", error_msg=err, last_log="\n".join(log)
            )
            return ScraperResult(fuente=self.fuente, error=err, log_lines=log)

        except Exception as exc:
            err = str(exc)
            _l(f"ERROR: {err}")
            upsert_scraper_status(
                self.fuente, estado="error", error_msg=err, last_log="\n".join(log)
            )
            return ScraperResult(fuente=self.fuente, error=err, log_lines=log)

    # ── Fetch de pagos ────────────────────────────────────────────────────────

    async def _fetch_all(
        self,
        client: httpx.AsyncClient,
        user_id: int,
        dias: int,
        existing_ids: set,
        log_fn,
        debug: bool = False,
    ) -> tuple[list[MovimientoRaw], dict]:
        """Trae egresos (payer) e ingresos (collector) del período."""
        # dias=1 → sólo hoy (ART); dias=2 → ayer y hoy; etc.
        today_art  = datetime.now(_ART).date()
        since_date = today_art - timedelta(days=dias - 1)
        since = f"{since_date}T00:00:00.000-03:00"
        until = f"{today_art}T23:59:59.999-03:00"

        movimientos: list[MovimientoRaw] = []
        stats = {"egresos": 0, "ingresos": 0, "skipped": 0}

        for role, sign, label in [
            ("payer.id",     +1, "egresos"),
            ("collector.id", -1, "ingresos"),
        ]:
            log_fn(f"Consultando {label} (últimos {dias} días) …")
            page_movs, skipped = await self._paginate(
                client, user_id, role, since, until, sign, existing_ids, log_fn, debug
            )
            movimientos.extend(page_movs)
            stats[label]      = len(page_movs)
            stats["skipped"] += skipped

        return movimientos, stats

    async def _paginate(
        self,
        client: httpx.AsyncClient,
        user_id: int,
        role_param: str,
        since: str,
        until: str,
        sign: int,
        existing_ids: set,
        log_fn,
        debug: bool = False,
    ) -> tuple[list[MovimientoRaw], int]:
        """Pagina /v1/payments/search y convierte resultados."""
        movs:        list[MovimientoRaw] = []
        skipped:     int = 0
        cc_skipped:  int = 0
        rej_skipped: int = 0
        offset:      int = 0

        # Statuses que descartamos: el pago no ocurrió o fue revertido.
        _SKIP_STATUSES = frozenset({"rejected", "cancelled", "charged_back", "refunded"})

        while True:
            params = {
                role_param:   user_id,
                "sort":       "date_created",
                "criteria":   "desc",
                "range":      "date_created",
                "begin_date": since,
                "end_date":   until,
                # Sin filtro de status: la API devuelve approved + in_process + pending.
                # Filtramos rejected/cancelled en código para no perder pagos recientes
                # que aún no fueron aprobados (ej. tarjeta prepaga T+0).
                "limit":      _PAGE_SIZE,
                "offset":     offset,
            }
            resp = await client.get(f"{_BASE}/v1/payments/search", params=params)
            resp.raise_for_status()
            data    = resp.json()
            results = data.get("results", [])
            if not results:
                break

            for payment in results:
                pid        = payment.get("id")
                pay_type   = payment.get("payment_type_id", "")
                op_type    = payment.get("operation_type", "")
                status     = payment.get("status", "")
                amount     = payment.get("transaction_amount", 0)
                reason     = (payment.get("reason") or payment.get("description") or "")[:30]
                payer_id   = (payment.get("payer") or {}).get("id", "?")
                coll_id    = payment.get("collector_id", "?")

                # Campos extra para debug: enriquecen la descripción de transferencias
                payer_email  = (payment.get("payer") or {}).get("email", "")
                payer_ident  = (payment.get("payer") or {}).get("identification") or {}
                payer_dni    = f"{payer_ident.get('type','')}:{payer_ident.get('number','')}" if payer_ident else ""
                ext_ref      = (payment.get("external_reference") or "")[:40]
                td           = payment.get("transaction_details") or {}
                td_ref       = (td.get("payment_method_reference_id") or "")[:40]
                td_bank      = (td.get("financial_institution") or "")

                def _dbg(tag: str) -> None:
                    if debug:
                        log_fn(
                            f"  [dbg] {tag:<12} id={pid} status={status} payer={payer_id}"
                            f" coll={coll_id} type={pay_type} op={op_type}"
                            f" amt={amount:.2f} reason={reason}"
                        )
                        if payer_email: log_fn(f"           payer_email={payer_email}")
                        if payer_dni:   log_fn(f"           payer_ident={payer_dni}")
                        if ext_ref:     log_fn(f"           ext_ref={ext_ref}")
                        if td_ref:      log_fn(f"           td_ref={td_ref}")
                        if td_bank:     log_fn(f"           td_bank={td_bank}")

                # Excluir pagos fallidos o revertidos
                if status in _SKIP_STATUSES:
                    rej_skipped += 1
                    _dbg("OMITIDO-ST")
                    continue

                # Excluir pagos con tarjeta de crédito: esos cargos ya aparecen
                # en el resumen de la tarjeta y se importan vía PDF.
                if pay_type == "credit_card":
                    cc_skipped += 1
                    _dbg("OMITIDO-CC")
                    continue

                # partition_transfer y account_fund: ambos aparecen en las dos queries
                # porque MP los asocia al mismo user_id en payer y collector.
                # account_fund = dinero que entra a la cuenta (depósito desde banco, etc.)
                # Siempre son ingresos → saltar en query de payer, capturar en collector.
                if op_type in ("partition_transfer", "account_fund") and sign == +1:
                    _dbg("DEFER-IN")
                    continue

                if pid and pid in existing_ids:
                    skipped += 1
                    _dbg("YA-EXISTE")
                    continue

                mov = self._payment_to_movimiento(payment, sign)
                if mov:
                    movs.append(mov)
                    if pid:
                        existing_ids.add(pid)
                    _dbg("NUEVO")
                else:
                    _dbg("SIN-DATOS")

            total  = data.get("paging", {}).get("total", 0)
            offset += len(results)
            if offset >= total or len(results) < _PAGE_SIZE:
                break

        cc_note  = f", {cc_skipped} tarjeta crédito omitidos"  if cc_skipped  else ""
        rej_note = f", {rej_skipped} rechazados/cancelados"    if rej_skipped else ""
        log_fn(f"  → {len(movs)} nuevos ({skipped} ya existían{cc_note}{rej_note})")
        return movs, skipped

    # ── Conversión de pagos ───────────────────────────────────────────────────

    def _payment_to_movimiento(self, p: dict, sign: int) -> Optional[MovimientoRaw]:
        """
        Convierte un objeto payment de la API en un único MovimientoRaw.

        sign = +1  → egreso  (user pagó  → monto positivo en nuestra convención)
        sign = -1  → ingreso (user cobró → monto negativo)
        """
        try:
            # Usar date_created (momento de la transacción, lo que muestra la app MP).
            # date_approved es la fecha de liquidación: para tarjeta prepaga es T+1,
            # lo que desplazaba la fecha un día hacia adelante.
            fecha_str = (p.get("date_created") or p.get("date_approved") or "")[:10]
            if not fecha_str or len(fecha_str) < 10:
                return None

            monto = float(p.get("transaction_amount", 0))
            if monto <= 0:
                return None

            moneda      = "USD" if p.get("currency_id") == "USD" else "ARS"
            monto_final = round(monto * sign, 2)

            desc = self._build_description(p, sign)
            if not desc:
                return None

            raw_data = self._build_raw_data(p, sign)
            return MovimientoRaw(
                fuente      = "mercadopago",
                fecha       = fecha_str,
                descripcion = desc,
                monto       = monto_final,
                moneda      = moneda,
                raw_data    = raw_data,
            )
        except Exception as exc:
            logger.warning("[mp] Error convirtiendo payment id=%s: %s", p.get("id"), exc)
            return None

    def _build_raw_data(self, p: dict, sign: int = +1) -> dict:
        """Construye el diccionario raw_data con todos los campos relevantes."""
        raw_data: dict = {
            "payment_id":      p.get("id"),
            "status":          p.get("status"),
            "operation_type":  p.get("operation_type"),
            "payment_method":  p.get("payment_method_id"),
            "payment_type_id": p.get("payment_type_id"),
            "installments":    p.get("installments"),
            "status_detail":   p.get("status_detail"),
            "collector_id":    p.get("collector_id"),
        }

        # Para ingresos (sign=-1): guardar datos del pagador
        if sign == -1:
            payer = p.get("payer") or {}
            first = (payer.get("first_name") or "").strip()
            last  = (payer.get("last_name")  or "").strip()
            nick  = (payer.get("nickname")   or "").strip()
            email = (payer.get("email")      or "").strip()
            payer_name = f"{first} {last}".strip() or nick
            if payer_name:
                raw_data["payer_name"]  = payer_name
            if email:
                raw_data["payer_email"] = email

        # Descriptor en extracto bancario (útil para identificar el comercio)
        stmt_desc = (p.get("statement_descriptor") or "").strip()
        if stmt_desc:
            raw_data["statement_descriptor"] = stmt_desc

        # Punto de interacción (QR/POS)
        poi = p.get("point_of_interaction") or {}
        poi_type = poi.get("type", "")
        if poi_type:
            raw_data["poi_type"] = poi_type
            biz = poi.get("business_info") or {}
            poi_name = (biz.get("sub_unit") or biz.get("unit") or "").strip()
            if poi_name:
                raw_data["poi_name"] = poi_name

        # Usuario default (Q2)
        default_usuario = getattr(self, "_default_usuario", "")
        if default_usuario:
            raw_data["usuario"] = default_usuario

        return raw_data

    def _build_description_base(self, p: dict, sign: int = +1) -> str:
        """
        Construye la descripción base sin sufijo de cuotas.

        Reglas explícitas (primer match gana):
          1. partition_transfer       → "Transferencia desde/hacia Reserva"
          2. account_fund             → "Depósito bancario"
          3. account_money+transfer   → "{sender} — Transferencia: {reason}" (sign=-1)
                                        "Transferencia: {reason}" (sign=+1)
          4. account_money+regular    → reason directo (si no es código técnico)
          5. Resto                    → lógica genérica: poi_name / merchant / reason /
                                        stmt_desc / op_label / "MercadoPago"
        """
        pay_type    = p.get("payment_type_id", "")
        op_type     = p.get("operation_type", "")
        _raw_reason = (p.get("reason") or p.get("description") or "").strip()

        # ── Helper: nombre del pagador (disponible en collector query, sign=-1) ──
        def _payer_name() -> str:
            payer = p.get("payer") or {}
            first = (payer.get("first_name") or "").strip()
            last  = (payer.get("last_name")  or "").strip()
            nick  = (payer.get("nickname")   or "").strip()
            email = (payer.get("email")      or "").strip()
            return f"{first} {last}".strip() or nick or email

        # ── Regla 1: partition_transfer ────────────────────────────────────────
        if op_type == "partition_transfer":
            return "Transferencia desde Reserva" if sign == -1 else "Transferencia hacia Reserva"

        # ── Regla 2: depósito bancario (bank_transfer + account_fund) ──────────
        if op_type == "account_fund":
            # Siempre es ingreso (se captura solo en collector query).
            # El motivo "Bank Transfer" es genérico; usamos etiqueta propia.
            return "Depósito bancario"

        # ── Regla 3: transferencia entre cuentas MP ────────────────────────────
        if pay_type == "account_money" and op_type == "money_transfer":
            label = f"Transferencia: {_raw_reason}" if _raw_reason else "Transferencia"
            if sign == -1:
                sender = _payer_name()
                return f"{sender} — {label}" if sender else label
            return label

        # ── Regla 3: pago regular con billetera → reason directo ───────────────
        if pay_type == "account_money" and op_type == "regular_payment":
            if _raw_reason and _raw_reason not in _TECHNICAL_CODES:
                return _raw_reason
            # reason vacío o código técnico → caer a lógica genérica abajo

        # ── Lógica genérica para otros tipos (QR/POS, e-commerce, etc.) ────────

        # Nombre del pagador (solo para ingresos no cubiertos por reglas anteriores)
        payer_name = ""
        if sign == -1:
            payer = p.get("payer") or {}
            first = (payer.get("first_name") or "").strip()
            last  = (payer.get("last_name")  or "").strip()
            nick  = (payer.get("nickname")   or "").strip()
            payer_name = f"{first} {last}".strip() or nick

        # Nombre del negocio desde el punto de interacción (QR/POS)
        poi_name = ""
        try:
            biz      = (p.get("point_of_interaction") or {}).get("business_info") or {}
            poi_name = (biz.get("sub_unit") or biz.get("unit") or "").strip()
        except Exception:
            pass

        # Nombre del ítem en additional_info (filtrar códigos técnicos)
        merchant = ""
        try:
            items = (p.get("additional_info") or {}).get("items") or []
            if items:
                candidate = (items[0].get("title") or "").strip()
                if candidate and candidate not in _TECHNICAL_CODES:
                    merchant = candidate
        except Exception:
            pass

        # Razón textual (descartar si es código técnico)
        reason = _raw_reason if (" " in _raw_reason and _raw_reason not in _TECHNICAL_CODES) else ""

        # Descriptor en extracto bancario
        stmt_desc = (p.get("statement_descriptor") or "").strip()

        # Etiqueta del tipo de operación
        op_label = {
            "regular_payment":    "Pago",
            "money_transfer":     "Transferencia",
            "recurring_payment":  "Pago recurrente",
            "account_fund":       "Carga de saldo",
            "investment":         "Inversión",
            "pos_payment":        "Pago QR",
            "checkout_pro":       "Compra online",
            "checkout_on":        "Compra online",
            "money_outflows":     "Transferencia saliente",
            "money_release":      "Liberación de fondos",
            "partition_transfer": "Transferencia interna",
        }.get(op_type, "")

        # Para ingresos: anteponer nombre del pagador
        if payer_name:
            extra = poi_name or merchant or reason or stmt_desc or op_label or ""
            return f"{payer_name} — {extra}" if extra else payer_name

        # Para egresos: mejor nombre comercial disponible
        best_name = poi_name or merchant or ""
        if best_name and reason and best_name.lower() not in reason.lower():
            return f"{best_name} — {reason}"
        if best_name:
            return best_name
        if reason:
            return reason
        if stmt_desc:
            return stmt_desc
        if op_label:
            return op_label
        return "MercadoPago"

    def _build_description(self, p: dict, sign: int = +1) -> str:
        """Descripción completa; agrega sufijo "(N cuotas)" si aplica."""
        base         = self._build_description_base(p, sign)
        installments = int(p.get("installments", 1) or 1)
        # Los pagos CC ya son excluidos antes de llegar aquí; este sufijo aplica
        # a cuotas de otros medios (débito diferido, etc.) si existieran.
        if installments > 1:
            base += f" ({installments} cuotas)"
        return base

    # ── Saldo ─────────────────────────────────────────────────────────────────

    async def _fetch_balance(
        self, client: httpx.AsyncClient, log_fn
    ) -> dict:
        """Consulta el saldo disponible de la cuenta."""
        try:
            resp = await client.get(f"{_BASE}/v1/account/balance")
            if resp.status_code == 200:
                data  = resp.json()
                saldo = float(data.get("available_balance", 0))
                log_fn(f"Saldo disponible: ${saldo:,.2f} ARS")
                return {"mercadopago": {"saldo_ars": saldo}}
            log_fn(f"Saldo: status {resp.status_code} — ignorado")
        except Exception as exc:
            log_fn(f"Saldo no disponible: {exc}")
        return {}

    # ── Stubs Selenium (nunca se invocan; BaseScraper los declara) ───────────

    def check_session(self, driver) -> bool:
        return False

    def do_login(self, driver, config: dict) -> None:
        pass

    def scrape(self, driver, config: dict) -> ScraperResult:
        return ScraperResult(fuente=self.fuente)


# ── Helpers DB ────────────────────────────────────────────────────────────────

def _get_existing_payment_ids(dias: int) -> set:
    """
    Devuelve el conjunto de payment_id ya almacenados en movimientos_raw
    para 'mercadopago' dentro del período consultado.
    Evita insertar duplicados en runs consecutivos.

    Incluye tanto IDs simples (int) como sub-IDs de cuotas (str "{id}_c{i}").
    """
    from scrapers_db import _conn

    since = (datetime.now(_ART).date() - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
    ids: set = set()
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT raw_data FROM movimientos_raw "
                "WHERE fuente='mercadopago' AND fecha >= ? "
                "AND estado IN ('new','imported','matched','ignored')",
                (since,),
            ).fetchall()
        for row in rows:
            if row["raw_data"]:
                try:
                    d = json.loads(row["raw_data"])
                    if pid := d.get("payment_id"):
                        ids.add(pid)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("[mp] No se pudo leer payment_ids existentes: %s", exc)
    return ids

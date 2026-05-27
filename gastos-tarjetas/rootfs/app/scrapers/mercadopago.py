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
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from .base import BaseScraper, MovimientoRaw, ScraperResult
from scrapers_db import upsert_scraper_status

logger = logging.getLogger(__name__)

_BASE        = "https://api.mercadopago.com"
_DIAS_DEFAULT = 60    # días hacia atrás a consultar si no se configura otro valor
_PAGE_SIZE    = 50    # máximo que acepta la API


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
                    client, user_id, dias, existing_ids, _l
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
                estado           = "ok",
                ultimo_ok        = now_iso,
                error_msg        = None,
                movimientos_nuevos = len(movimientos),
                saldo_ars        = saldos.get("mercadopago", {}).get("saldo_ars"),
                last_log         = "\n".join(log),
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
    ) -> tuple[list[MovimientoRaw], dict]:
        """Trae egresos (payer) e ingresos (collector) del período."""
        since = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime(
            "%Y-%m-%dT00:00:00.000-00:00"
        )
        until = datetime.now(timezone.utc).strftime("%Y-%m-%dT23:59:59.999-00:00")

        movimientos: list[MovimientoRaw] = []
        stats = {"egresos": 0, "ingresos": 0, "skipped": 0}

        for role, sign, label in [
            ("payer.id",     +1, "egresos"),
            ("collector.id", -1, "ingresos"),
        ]:
            log_fn(f"Consultando {label} (últimos {dias} días) …")
            page_movs, skipped = await self._paginate(
                client, user_id, role, since, until, sign, existing_ids, log_fn
            )
            movimientos.extend(page_movs)
            stats[label]  = len(page_movs)
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
    ) -> tuple[list[MovimientoRaw], int]:
        """Pagina /v1/payments/search y convierte resultados."""
        movs:    list[MovimientoRaw] = []
        skipped: int = 0
        offset:  int = 0

        while True:
            params = {
                role_param:     user_id,
                "sort":         "date_created",
                "criteria":     "desc",
                "range":        "date_created",
                "begin_date":   since,
                "end_date":     until,
                "status":       "approved",
                "limit":        _PAGE_SIZE,
                "offset":       offset,
            }
            resp = await client.get(f"{_BASE}/v1/payments/search", params=params)
            resp.raise_for_status()
            data    = resp.json()
            results = data.get("results", [])
            if not results:
                break

            for payment in results:
                pid = payment.get("id")
                if pid and pid in existing_ids:
                    skipped += 1
                    continue
                mov = self._payment_to_movimiento(payment, sign)
                if mov:
                    movs.append(mov)
                    if pid:
                        existing_ids.add(pid)   # evitar duplicados dentro de la misma tanda

            total  = data.get("paging", {}).get("total", 0)
            offset += len(results)
            if offset >= total or len(results) < _PAGE_SIZE:
                break

        log_fn(f"  → {len(movs)} nuevos ({skipped} ya existían)")
        return movs, skipped

    # ── Conversión de pagos ───────────────────────────────────────────────────

    def _payment_to_movimiento(self, p: dict, sign: int) -> Optional[MovimientoRaw]:
        """
        Convierte un objeto payment de la API en MovimientoRaw.

        sign = +1  → egreso  (user pagó  → monto positivo en nuestra convención)
        sign = -1  → ingreso (user cobró → monto negativo)
        """
        try:
            # Fecha: usar date_approved si existe, si no date_created
            fecha_str = (p.get("date_approved") or p.get("date_created") or "")[:10]
            if not fecha_str or len(fecha_str) < 10:
                return None

            monto = float(p.get("transaction_amount", 0))
            if monto <= 0:
                return None

            moneda      = "USD" if p.get("currency_id") == "USD" else "ARS"
            monto_final = round(monto * sign, 2)

            desc = self._build_description(p)
            if not desc:
                return None

            raw_data = {
                "payment_id":     p.get("id"),
                "operation_type": p.get("operation_type"),
                "payment_method": p.get("payment_method_id"),
                "installments":   p.get("installments"),   # cuotas de tarjeta (si aplica)
                "status_detail":  p.get("status_detail"),
            }

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

    def _build_description(self, p: dict) -> str:
        """
        Construye una descripción legible a partir del objeto payment.

        Prioridad:
          1. Nombre del ítem en additional_info (e.g. nombre del comercio en QR)
          2. reason / description del pago
          3. Etiqueta del tipo de operación
        """
        # Nombre del comercio / ítem (QR, e-commerce)
        merchant = ""
        try:
            items = (p.get("additional_info") or {}).get("items") or []
            if items:
                merchant = (items[0].get("title") or "").strip()
        except Exception:
            pass

        # Razón textual del pago
        reason = (p.get("reason") or p.get("description") or "").strip()

        # Tipo de operación como fallback
        op_label = {
            "regular_payment":   "Pago",
            "money_transfer":    "Transferencia",
            "recurring_payment": "Pago recurrente",
            "account_fund":      "Carga de saldo",
            "investment":        "Inversión",
            "pos_payment":       "Pago QR",
            "checkout_pro":      "Compra online",
        }.get(p.get("operation_type", ""), "")

        # Cuotas de tarjeta si aplica
        installments = p.get("installments", 1) or 1
        cuota_suffix = f" ({installments} cuotas)" if installments > 1 else ""

        # Construir descripción
        if merchant and reason and merchant.lower() not in reason.lower():
            base = f"{merchant} — {reason}"
        elif merchant:
            base = merchant
        elif reason:
            base = reason
        elif op_label:
            base = op_label
        else:
            base = "MercadoPago"

        return base + cuota_suffix

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
    """
    from datetime import datetime, timedelta
    from scrapers_db import _conn

    since = (datetime.utcnow() - timedelta(days=dias)).strftime("%Y-%m-%d")
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

"""
Scraper Cocos Capital — API REST.

No usa Selenium. Autenticación JWT (Supabase GoTrue) con 2FA TOTP y refresh automático.
Usa cloudscraper para bypass del WAF Cloudflare que protege api.cocos.capital.

Cómo obtener el TOTP secret:
  1. En la app/web de Cocos, ir a Seguridad → Autenticación de dos factores
  2. Al configurar el TOTP (o reconfigurar), se muestra un QR.
  3. Escanearlo con un lector de QR (no con el authenticator): obtener la URI completa.
     URI ejemplo: otpauth://totp/app.cocos.capital:tu@mail.com?...&secret=ABCDEFGHIJKLMNOP&...
  4. Copiar el valor del parámetro `secret=` → pegarlo en la UI del add-on.

Endpoints usados:
  POST auth/v1/token?grant_type=password        → login inicial (email+password)
  GET  auth/v1/factors/default                  → obtener factor 2FA disponible
  POST auth/v1/factors/{factor_id}/challenge    → iniciar challenge TOTP
  POST auth/v1/factors/{factor_id}/verify       → verificar código TOTP → token final
  POST auth/v1/token?grant_type=refresh_token   → refresh de sesión (evita re-login)
  GET  api/v1/users/me                          → account_id (id_accounts[0])
  GET  api/v1/wallet/cash_movements             → movimientos de cuenta (paginado, limit/offset)
                                                   Respuesta: {data:[{executionDate, balance,
                                                   cashMovements:[...]}]}. data[0].balance = saldo ARS.
"""

import asyncio
import json as _json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

try:
    import cloudscraper as _cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

try:
    import pyotp as _pyotp
    _HAS_PYOTP = True
except ImportError:
    _HAS_PYOTP = False

from .base import BaseScraper, MovimientoRaw, ScraperResult
from scrapers_db import upsert_scraper_status

logger = logging.getLogger(__name__)

_BASE         = "https://api.cocos.capital"
_DIAS_DEFAULT = 60
_ART          = timezone(timedelta(hours=-3))

# Anon/API key de Supabase de la app Cocos Capital (clave pública embebida en el JS).
_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".ewogICJyb2xlIjogImFub24iLAogICJpc3MiOiAic3VwYWJhc2UiLAogICJpYXQiOiAxNzA0NjgyODAwLAogICJleHAiOiAxODYyNTM1NjAwCn0"
    ".f0w62k0q0eyyGBDkAP7vUUEg_Ingb9YbOlhsGCC4R3c"
)

_LIMIT = 50  # registros por página en cash_movements


class CocosScraper(BaseScraper):
    fuente       = "cocos"
    nombre       = "Cocos Capital"
    login_origin = "https://app.cocos.capital"

    # ── Punto de entrada (override: REST, no Selenium) ────────────────────────

    async def run(self, config: dict) -> ScraperResult:
        now_iso = datetime.utcnow().isoformat()
        upsert_scraper_status(self.fuente, estado="running", ultimo_run=now_iso)

        if not _HAS_CLOUDSCRAPER:
            err = "cloudscraper no está instalado — agregalo a requirements.txt"
            upsert_scraper_status(self.fuente, estado="error", error_msg=err)
            return ScraperResult(fuente=self.fuente, error=err)

        if not _HAS_PYOTP:
            err = "pyotp no está instalado — agregalo a requirements.txt"
            upsert_scraper_status(self.fuente, estado="error", error_msg=err)
            return ScraperResult(fuente=self.fuente, error=err)

        result = await asyncio.to_thread(self._run_sync, config, now_iso)
        return result

    def _run_sync(self, config: dict, now_iso: str) -> ScraperResult:
        """Lógica completa en sync usando cloudscraper (necesario para bypass Cloudflare)."""
        log: list[str] = []

        def _l(msg: str) -> None:
            logger.info("[cocos] %s", msg)
            log.append(msg)

        session = _cloudscraper.create_scraper()
        session.headers.update({
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Content-Type": "application/json",
        })

        try:
            token, account_id = self._ensure_token_sync(session, config, _l)

            api_hdrs = {
                "Authorization": f"Bearer {token}",
                "x-account-id":  account_id,
                "Content-Type":  "application/json",
            }

            dias            = int(config.get("dias") or _DIAS_DEFAULT)
            debug_log       = bool(config.get("debug_log"))
            default_usuario = (config.get("usuario") or "").strip()

            today_art  = datetime.now(_ART).date()
            since_date = today_art - timedelta(days=dias - 1)

            movimientos, saldo_ars = self._fetch_movements_sync(
                session, api_hdrs, since_date, today_art, default_usuario, _l, debug_log
            )
            saldos = {"cocos": {"saldo_ars": saldo_ars, "saldo_usd": None}}

            upsert_scraper_status(
                self.fuente,
                estado             = "ok",
                ultimo_ok          = now_iso,
                error_msg          = None,
                movimientos_nuevos = len(movimientos),
                saldo_ars          = saldo_ars,
                last_log           = "\n".join(log),
            )
            return ScraperResult(
                fuente      = self.fuente,
                movimientos = movimientos,
                saldos      = saldos,
                log_lines   = log,
            )

        except Exception as exc:
            err = str(exc)
            _l(f"ERROR: {err}")
            upsert_scraper_status(
                self.fuente, estado="error", error_msg=err, last_log="\n".join(log)
            )
            return ScraperResult(fuente=self.fuente, error=err, log_lines=log)

    # ── Token management ──────────────────────────────────────────────────────

    def _load_session(self) -> Optional[dict]:
        if not os.path.exists(self.session_path):
            return None
        try:
            with open(self.session_path) as f:
                data = _json.load(f)
            expires_at_raw = data.get("expires_at")
            if expires_at_raw:
                exp = datetime.fromisoformat(expires_at_raw)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) + timedelta(minutes=5) >= exp:
                    return {"refresh_token": data.get("refresh_token")}
            return data
        except Exception as exc:
            logger.warning("[cocos] Error leyendo sesión: %s", exc)
            return None

    def _save_session(self, token_resp: dict, account_id: str = "") -> None:
        try:
            expires_at_raw = token_resp.get("expires_at")
            if isinstance(expires_at_raw, (int, float)):
                expires_at = datetime.fromtimestamp(expires_at_raw, tz=timezone.utc).isoformat()
            elif expires_at_raw:
                expires_at = str(expires_at_raw)
            else:
                expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
            with open(self.session_path, "w") as f:
                _json.dump({
                    "access_token":  token_resp.get("access_token"),
                    "refresh_token": token_resp.get("refresh_token"),
                    "expires_at":    expires_at,
                    "account_id":    account_id,
                }, f)
        except Exception as exc:
            logger.warning("[cocos] Error guardando sesión: %s", exc)

    def _ensure_token_sync(self, session, config: dict, log_fn) -> tuple[str, str]:
        """Devuelve (access_token, account_id)."""
        saved = self._load_session()

        if saved and saved.get("access_token"):
            log_fn("Sesión Cocos vigente — reutilizando")
            return saved["access_token"], saved.get("account_id") or ""

        if saved and saved.get("refresh_token"):
            log_fn("Token Cocos expirado — intentando refresh…")
            try:
                resp = session.post(
                    f"{_BASE}/auth/v1/token",
                    params={"grant_type": "refresh_token"},
                    json={"refresh_token": saved["refresh_token"]},
                    headers=_anon_headers(),
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    account_id = saved.get("account_id") or ""
                    self._save_session(data, account_id)
                    log_fn("Token Cocos refrescado OK")
                    return data["access_token"], account_id
                log_fn(f"Refresh falló (HTTP {resp.status_code}) — re-login")
            except Exception as exc:
                log_fn(f"Refresh error: {exc} — re-login")

        return self._full_login_sync(session, config, log_fn)

    def _full_login_sync(self, session, config: dict, log_fn) -> tuple[str, str]:
        email       = (config.get("email")       or "").strip()
        password    = (config.get("password")    or "").strip()
        totp_secret = (config.get("totp_secret") or "").strip()
        if not email or not password:
            raise ValueError("Credenciales Cocos incompletas (email y/o contraseña vacíos)")
        if not totp_secret:
            raise ValueError(
                "TOTP secret no configurado. "
                "Ver instrucciones en Config → Scrapers → Cocos Capital."
            )

        # 1. Login email+password
        log_fn("Autenticando en Cocos Capital…")
        resp = session.post(
            f"{_BASE}/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password, "gotrue_meta_security": {}},
            headers=_anon_headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"Login Cocos falló — HTTP {resp.status_code}: {resp.text[:300]}")
        phase1 = resp.json()
        phase1_token = phase1.get("access_token")
        if not phase1_token:
            raise ValueError(f"Login Cocos: access_token no encontrado. Respuesta: {resp.text[:300]}")

        auth_hdrs = {**_anon_headers(), "Authorization": f"Bearer {phase1_token}"}

        # 2. Obtener factor 2FA
        resp = session.get(f"{_BASE}/auth/v1/factors/default", headers=auth_hdrs, timeout=15)
        if resp.status_code != 200:
            raise ValueError(f"Cocos 2FA factors falló — HTTP {resp.status_code}: {resp.text[:200]}")
        factor_data = resp.json()
        factor_id   = factor_data.get("id")
        if not factor_id:
            raise ValueError(f"Cocos 2FA: factor_id no encontrado. Respuesta: {resp.text[:200]}")

        # 3. Iniciar challenge
        resp = session.post(
            f"{_BASE}/auth/v1/factors/{factor_id}/challenge",
            headers=auth_hdrs,
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            raise ValueError(f"Cocos 2FA challenge falló — HTTP {resp.status_code}: {resp.text[:200]}")

        # 4. Verificar con código TOTP
        totp_code = _pyotp.TOTP(totp_secret).now()
        log_fn("Verificando 2FA TOTP…")
        resp = session.post(
            f"{_BASE}/auth/v1/factors/{factor_id}/verify",
            json={"challenge_id": "_", "code": totp_code},
            headers=auth_hdrs,
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"Cocos 2FA verify falló — HTTP {resp.status_code}: {resp.text[:300]}")
        phase2 = resp.json()
        final_token = phase2.get("access_token")
        if not final_token:
            raise ValueError(f"Cocos 2FA: access_token final no encontrado. Respuesta: {resp.text[:200]}")

        # 5. Obtener account_id desde api/v1/users/me
        api_hdrs = {
            "Authorization": f"Bearer {final_token}",
            "Content-Type":  "application/json",
        }
        account_id = ""
        try:
            resp = session.get(f"{_BASE}/api/v1/users/me", headers=api_hdrs, timeout=15)
            if resp.status_code == 200:
                me = resp.json()
                accounts = me.get("id_accounts") or []
                if accounts:
                    account_id = str(accounts[0])
                    log_fn(f"Account ID: {account_id}")
                else:
                    log_fn(f"  [!] id_accounts vacío en /api/v1/users/me: {resp.text[:200]}")
            else:
                log_fn(f"  [!] /api/v1/users/me — HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            log_fn(f"  [!] Error obteniendo account_id: {exc}")

        self._save_session(phase2, account_id)
        log_fn("Login Cocos OK — sesión guardada")
        return final_token, account_id

    # ── Movimientos ───────────────────────────────────────────────────────────

    def _fetch_movements_sync(
        self, session, hdrs: dict, since: date, until: date,
        default_usuario: str, log_fn, debug: bool = False,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:
        """Returns (movimientos, saldo_ars). Saldo viene de data[0].balance del primer page."""
        log_fn(f"Consultando movimientos Cocos ({since} → {until})…")

        all_items: list[dict] = []
        saldo_ars: Optional[float] = None
        offset = 0

        while True:
            resp = session.get(
                f"{_BASE}/api/v1/wallet/cash_movements",
                params={"currency": "ARS", "limit": _LIMIT, "offset": offset},
                headers=hdrs,
                timeout=30,
            )
            if resp.status_code == 401:
                self.clear_session()
                raise ValueError("Sesión Cocos inválida (401) — sesión eliminada, el próximo run re-autenticará.")
            if resp.status_code != 200:
                log_fn(f"  [!] Movimientos — HTTP {resp.status_code}: {resp.text[:300]}")
                return [], saldo_ars

            try:
                data = resp.json()
            except Exception as exc:
                log_fn(f"  [!] Respuesta no es JSON: {exc} — body: {resp.text[:300]}")
                return [], saldo_ars

            day_groups = data.get("data") if isinstance(data, dict) else None
            if day_groups is None:
                log_fn(f"  [!] Estructura inesperada (offset={offset}): claves={list(data.keys()) if isinstance(data, dict) else type(data).__name__} — {_json.dumps(data)[:300]}")
                break

            if offset == 0:
                log_fn(f"  [dbg] días recibidos: {len(day_groups)}, claves respuesta: {list(data.keys())}")
                if day_groups:
                    log_fn(f"  [dbg] primer día: {day_groups[0].get('executionDate')} — {len(day_groups[0].get('cashMovements') or [])} movs, balance={day_groups[0].get('balance')}")
                    raw_bal = day_groups[0].get("balance")
                    if raw_bal is not None:
                        saldo_ars = float(raw_bal)

            batch: list[dict] = []
            for group in day_groups:
                batch.extend(group.get("cashMovements") or [])

            all_items.extend(batch)

            total_items = int(batch[0].get("total_items") or 0) if batch else 0
            if not batch or len(all_items) >= total_items or len(batch) < _LIMIT:
                break
            offset += _LIMIT

        if not all_items:
            log_fn(f"  → API devolvió 0 items (saldo_ars={saldo_ars})")
            return [], saldo_ars

        if debug:
            log_fn(f"  [dbg] estructura primer movimiento: {_json.dumps(all_items[0])[:600]}")

        since_str = since.isoformat()
        until_str = until.isoformat()
        movimientos: list[MovimientoRaw] = []
        skipped = 0
        for item in all_items:
            # Filtro de fecha client-side (la API no filtra por date_from/date_to)
            fecha_item = (item.get("execution_date") or "")[:10]
            if fecha_item and (fecha_item < since_str or fecha_item > until_str):
                continue
            mov, reason = self._movement_to_raw(item, default_usuario)
            if mov is None:
                skipped += 1
                if debug:
                    log_fn(f"  [!] DROP {reason}: {_json.dumps(item)[:200]}")
                continue
            movimientos.append(mov)

        log_fn(f"  → {len(movimientos)} movimientos, saldo ARS: {saldo_ars} ({skipped} omitidos)")
        return movimientos, saldo_ars

    def _movement_to_raw(
        self, item: dict, default_usuario: str
    ) -> tuple[Optional[MovimientoRaw], str]:
        try:
            # Dedup key: id_cash_movement > id_ticket > sintético
            id_cash   = item.get("id_cash_movement")
            id_ticket = (item.get("id_ticket") or "").strip()
            if id_cash is not None:
                uid = f"cm_{id_cash}"
            elif id_ticket:
                uid = f"tk_{id_ticket}"
            else:
                qty  = item.get("quantity", 0)
                dt   = (item.get("execution_date") or "")[:10]
                acct = item.get("id_account", "")
                uid  = f"syn_{acct}_{dt}_{qty}"

            fecha = (item.get("execution_date") or item.get("settlement_date") or "")[:10]
            if not fecha or len(fecha) < 10:
                return None, "sin_fecha"

            quantity = float(item.get("quantity") or 0)
            if quantity == 0:
                return None, "monto=0"

            # quantity < 0 = salida (egreso); sign convention: monto > 0 = egreso
            monto = round(-quantity, 2)

            description = (item.get("description") or "").strip()
            detail      = (item.get("detail") or "").strip()
            if detail and detail.lower() != description.lower():
                full_desc = f"{description} — {detail}" if description else detail
            else:
                full_desc = description or "Movimiento Cocos"

            currency_raw = (item.get("id_currency") or "ARS").upper()
            moneda = "USD" if "USD" in currency_raw else "ARS"

            raw_data: dict = {
                "transaction_id": uid,
                "operation_type": item.get("operation_type"),
                "source":         item.get("source"),
                "id_concept":     item.get("id_concept"),
            }
            if default_usuario:
                raw_data["usuario"] = default_usuario

            return MovimientoRaw(
                fuente      = "cocos",
                fecha       = fecha,
                descripcion = full_desc,
                monto       = monto,
                moneda      = moneda,
                raw_data    = raw_data,
            ), ""

        except Exception as exc:
            return None, f"excepcion: {exc}"

    # ── Stubs Selenium (no aplican: scraper REST puro) ───────────────────────

    def check_session(self, driver) -> bool:
        return False

    def do_login(self, driver, config: dict) -> None:
        pass

    def scrape(self, driver, config: dict) -> ScraperResult:
        return ScraperResult(fuente=self.fuente)


def _anon_headers() -> dict:
    return {
        "Apikey":        _ANON_KEY,
        "Authorization": f"Bearer {_ANON_KEY}",
        "Content-Type":  "application/json",
    }

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
  GET  api/v1/transfers?date_from=&date_to=     → movimientos de cuenta
  GET  api/v1/wallet/portfolio                  → tenencias y saldo ARS/USD
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

_INGRESO_TYPES = frozenset({
    "deposit", "income", "credit", "acreditacion", "cobro",
    "dividendo", "intereses", "renta", "transfer_in",
})


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
            token = self._ensure_token_sync(session, config, _l)

            api_hdrs = {
                "apikey":        "",
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            }

            dias            = int(config.get("dias") or _DIAS_DEFAULT)
            debug_log       = bool(config.get("debug_log"))
            default_usuario = (config.get("usuario") or "").strip()

            today_art  = datetime.now(_ART).date()
            since_date = today_art - timedelta(days=dias - 1)

            movimientos = self._fetch_movements_sync(
                session, api_hdrs, since_date, today_art, default_usuario, _l, debug_log
            )
            saldos = self._fetch_saldos_sync(session, api_hdrs, _l, debug_log)

            upsert_scraper_status(
                self.fuente,
                estado             = "ok",
                ultimo_ok          = now_iso,
                error_msg          = None,
                movimientos_nuevos = len(movimientos),
                saldo_ars          = (saldos.get("cocos") or {}).get("saldo_ars"),
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

    def _save_session(self, token_resp: dict) -> None:
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
                }, f)
        except Exception as exc:
            logger.warning("[cocos] Error guardando sesión: %s", exc)

    def _ensure_token_sync(self, session, config: dict, log_fn) -> str:
        saved = self._load_session()

        if saved and saved.get("access_token"):
            log_fn("Sesión Cocos vigente — reutilizando")
            return saved["access_token"]

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
                    self._save_session(data)
                    log_fn("Token Cocos refrescado OK")
                    return data["access_token"]
                log_fn(f"Refresh falló (HTTP {resp.status_code}) — re-login")
            except Exception as exc:
                log_fn(f"Refresh error: {exc} — re-login")

        return self._full_login_sync(session, config, log_fn)

    def _full_login_sync(self, session, config: dict, log_fn) -> str:
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

        self._save_session(phase2)
        log_fn("Login Cocos OK — sesión guardada")
        return final_token

    # ── Movimientos ───────────────────────────────────────────────────────────

    def _fetch_movements_sync(
        self, session, hdrs: dict, since: date, until: date,
        default_usuario: str, log_fn, debug: bool = False,
    ) -> list[MovimientoRaw]:
        log_fn(f"Consultando movimientos Cocos ({since} → {until})…")
        resp = session.get(
            f"{_BASE}/api/v1/transfers",
            params={"date_from": since.isoformat(), "date_to": until.isoformat()},
            headers=hdrs,
            timeout=30,
        )
        if resp.status_code == 401:
            self.clear_session()
            raise ValueError("Sesión Cocos inválida (401) — sesión eliminada, el próximo run re-autenticará.")
        if resp.status_code != 200:
            log_fn(f"  [!] Movimientos — HTTP {resp.status_code}: {resp.text[:200]}")
            return []

        data  = resp.json()
        items = (
            data if isinstance(data, list)
            else data.get("data") or data.get("movements") or data.get("transfers") or []
        )

        if not items:
            log_fn("  → Sin movimientos en el período")
            return []

        if debug:
            log_fn(f"  [dbg] estructura primer movimiento: {_json.dumps(items[0])[:600]}")

        movimientos: list[MovimientoRaw] = []
        skipped = 0
        for item in items:
            mov, reason = self._movement_to_raw(item, default_usuario)
            if mov is None:
                skipped += 1
                if debug:
                    log_fn(f"  [!] DROP {reason}: {_json.dumps(item)[:200]}")
                continue
            movimientos.append(mov)

        log_fn(f"  → {len(movimientos)} movimientos ({skipped} omitidos)")
        return movimientos

    def _movement_to_raw(
        self, item: dict, default_usuario: str
    ) -> tuple[Optional[MovimientoRaw], str]:
        try:
            uid = (
                item.get("id") or item.get("extId") or item.get("ext_id")
                or item.get("transactionId") or item.get("transaction_id")
            )

            fecha = (
                item.get("date") or item.get("createdAt") or item.get("created_at")
                or item.get("settlementDate") or item.get("settlement_date") or ""
            )[:10]
            if not fecha or len(fecha) < 10:
                return None, "sin_fecha"

            amount_raw = (
                item.get("amount") or item.get("net") or item.get("netAmount")
                or item.get("net_amount") or 0
            )
            monto = abs(float(amount_raw))
            if monto <= 0:
                return None, f"monto={monto}"

            item_type = (
                item.get("type") or item.get("operationType") or item.get("operation_type") or ""
            ).lower()

            description = (
                item.get("description") or item.get("concept") or item.get("label")
                or item.get("name") or item_type or "Movimiento Cocos"
            ).strip()

            if isinstance(amount_raw, (int, float)) and float(amount_raw) < 0:
                sign = -1
            elif item_type in _INGRESO_TYPES:
                sign = -1
            else:
                sign = +1

            monto_final = round(monto * sign, 2)

            currency_raw = (item.get("currency") or item.get("moneda") or "ARS").upper()
            moneda = "USD" if "USD" in currency_raw else "ARS"

            raw_data: dict = {"transaction_id": uid, "type": item_type}
            if default_usuario:
                raw_data["usuario"] = default_usuario

            return MovimientoRaw(
                fuente      = "cocos",
                fecha       = fecha,
                descripcion = description,
                monto       = monto_final,
                moneda      = moneda,
                raw_data    = raw_data,
            ), ""

        except Exception as exc:
            return None, f"excepcion: {exc}"

    # ── Saldos ────────────────────────────────────────────────────────────────

    def _fetch_saldos_sync(
        self, session, hdrs: dict, log_fn, debug: bool = False,
    ) -> dict:
        log_fn("Consultando portfolio Cocos…")
        try:
            resp = session.get(f"{_BASE}/api/v1/wallet/portfolio", headers=hdrs, timeout=20)
            if resp.status_code != 200:
                log_fn(f"  [!] Portfolio — HTTP {resp.status_code}: {resp.text[:150]}")
                return {}
            data = resp.json()

            if debug:
                log_fn(f"  [dbg] portfolio (primeros 600 chars): {_json.dumps(data)[:600]}")

            saldo_ars: Optional[float] = None
            saldo_usd: Optional[float] = None

            if isinstance(data, dict):
                for key in ("cash", "efectivo", "available", "liquidado", "saldo"):
                    val = data.get(key)
                    if val is None:
                        continue
                    if isinstance(val, (int, float)):
                        saldo_ars = float(val)
                        break
                    if isinstance(val, dict):
                        ars_v = val.get("ARS") or val.get("ars") or val.get("pesos")
                        usd_v = val.get("USD") or val.get("usd") or val.get("dolares")
                        if ars_v is not None:
                            saldo_ars = float(ars_v)
                        if usd_v is not None:
                            saldo_usd = float(usd_v)
                        break

            log_fn(f"  → Saldo ARS: {saldo_ars}, USD: {saldo_usd}")
            return {"cocos": {"saldo_ars": saldo_ars, "saldo_usd": saldo_usd}}

        except Exception as exc:
            log_fn(f"  [!] Error obteniendo portfolio: {exc}")
            return {}

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

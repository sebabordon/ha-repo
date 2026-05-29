"""
Scraper InvertirOnline — API REST.

No usa Selenium. Autenticación OAuth2 (grant_type=password) con refresh automático.

Funcionalidad:
  1. Autenticar y obtener access_token + refresh_token (expiry 1 hora)
  2. Consultar portafolio → saldo_ars (posiciones + cash ARS) y saldo_usd (posiciones USD)
  3. Opcionalmente importar operaciones terminadas como movimientos

Endpoints:
  POST /token                             → OAuth2 password grant / refresh
  GET  /api/v2/portafolio/{pais}          → holdings + estado de cuenta
  GET  /api/v2/operaciones                → operaciones terminadas (opt.)

Credenciales:
  usuario     → usuario IOL (email o alias)
  password    → contraseña IOL
  dias        → días a consultar para operaciones (default 60)
  importar_operaciones → checkbox: importar compras/ventas como movimientos
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from .base import BaseScraper, MovimientoRaw, ScraperResult
from scrapers_db import upsert_scraper_status

logger = logging.getLogger(__name__)

_BASE         = "https://api.invertironline.com"
_TOKEN_URL    = f"{_BASE}/token"
_PAIS         = "argentina"
_DIAS_DEFAULT = 60

_ART = timezone(timedelta(hours=-3))

_MONEDA_MAP = {
    "peso_argentino":       "ARS",
    "dolar_estadounidense": "USD",
}

_TIPO_MAP = {
    "acciones":                    "Acción",
    "cedears":                     "CEDEAR",
    "fondos_comunes_de_inversion": "FCI",
    "titulos_publicos":            "Bono",
    "obligaciones_negociables":    "ON",
    "cauciones":                   "Caución",
    "opciones":                    "Opción",
    "futuros":                     "Futuro",
}

# Tipos de operación que representan ingresos (signo negativo en nuestra convención)
_SIGN_INGRESO = ("venta", "cobro", "acreditaci", "dividendo", "renta")


class InvertirOnlineScraper(BaseScraper):
    fuente       = "invertironline"
    nombre       = "InvertirOnline"
    login_origin = "https://api.invertironline.com"

    # ── Token management ──────────────────────────────────────────────────────

    def _load_token(self) -> Optional[dict]:
        """Carga el token guardado. Devuelve None si no existe o está a ≤5 min de expirar."""
        if not os.path.exists(self.session_path):
            return None
        try:
            with open(self.session_path) as f:
                data = json.load(f)
            expires_at = data.get("expires_at")
            if expires_at:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) + timedelta(minutes=5) >= exp:
                    return None
            return data
        except Exception as exc:
            logger.warning("[iol] Error leyendo token guardado: %s", exc)
            return None

    def _save_token(self, token_resp: dict) -> None:
        try:
            expires_in = int(token_resp.get("expires_in", 3600))
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()
            os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
            with open(self.session_path, "w") as f:
                json.dump({
                    "access_token":  token_resp.get("access_token"),
                    "refresh_token": token_resp.get("refresh_token"),
                    "expires_at":    expires_at,
                }, f)
        except Exception as exc:
            logger.warning("[iol] Error guardando token: %s", exc)

    async def _ensure_token(
        self,
        client: httpx.AsyncClient,
        config: dict,
        log_fn,
    ) -> str:
        """Devuelve un access_token válido (cache → refresh → login completo)."""
        saved = self._load_token()
        if saved and saved.get("access_token"):
            log_fn("Token guardado vigente — reutilizando")
            return saved["access_token"]

        if saved and saved.get("refresh_token"):
            log_fn("Token expirado — intentando refresh…")
            try:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type":    "refresh_token",
                        "refresh_token": saved["refresh_token"],
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    token_data = resp.json()
                    self._save_token(token_data)
                    log_fn("Token refrescado OK")
                    return token_data["access_token"]
                log_fn(f"Refresh falló (HTTP {resp.status_code}) — re-login")
            except Exception as exc:
                log_fn(f"Refresh error: {exc} — re-login")

        log_fn("Autenticando con usuario/contraseña…")
        usuario  = (config.get("usuario")  or "").strip()
        password = (config.get("password") or "").strip()
        if not usuario or not password:
            raise ValueError("Credenciales IOL incompletas (usuario y/o contraseña vacíos)")

        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "password",
                "username":   usuario,
                "password":   password,
                "scope":      "desktop",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(
                f"Login IOL falló — HTTP {resp.status_code}: {resp.text[:300]}"
            )
        token_data = resp.json()
        self._save_token(token_data)
        log_fn("Login OK — token obtenido")
        return token_data["access_token"]

    # ── Punto de entrada (override: async REST, no Selenium) ──────────────────

    async def run(self, config: dict) -> ScraperResult:
        now_iso = datetime.utcnow().isoformat()
        upsert_scraper_status(self.fuente, estado="running", ultimo_run=now_iso)
        log: list[str] = []

        def _l(msg: str) -> None:
            logger.info("[iol] %s", msg)
            log.append(msg)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self._ensure_token(client, config, _l)
                hdrs  = {"Authorization": f"Bearer {token}"}

                _l(f"Consultando portafolio ({_PAIS})…")
                resp = await client.get(
                    f"{_BASE}/api/v2/portafolio/{_PAIS}", headers=hdrs
                )
                if resp.status_code == 401:
                    self.clear_session()
                    raise ValueError(
                        "Token inválido (401) — sesión eliminada, el próximo run hará re-login"
                    )
                resp.raise_for_status()

                saldo_ars, saldo_usd = self._process_portfolio(resp.json(), _l)

                movimientos: list[MovimientoRaw] = []
                if config.get("importar_operaciones"):
                    dias = int(config.get("dias") or _DIAS_DEFAULT)
                    movimientos = await self._fetch_operaciones(client, hdrs, dias, _l)

            saldos = {self.fuente: {"saldo_ars": saldo_ars, "saldo_usd": saldo_usd}}
            self._persist_saldos(saldos)

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
                saldo_ars          = saldo_ars,
                saldo_usd          = saldo_usd,
                last_log           = "\n".join(log),
            )
            return result

        except httpx.HTTPStatusError as exc:
            err = f"Error HTTP {exc.response.status_code}: {exc.response.text[:300]}"
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

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def _process_portfolio(self, portfolio: dict, log_fn) -> tuple[float, float]:
        """
        Suma el valor de los activos y el efectivo por moneda.

        saldo_ars = Σ valorizado(ARS) + efectivo en cuenta (ARS)
        saldo_usd = Σ valorizado(USD)
        """
        activos       = portfolio.get("activos") or []
        estado_cuenta = portfolio.get("estado_cuenta") or {}

        val_ars = 0.0
        val_usd = 0.0

        for a in activos:
            moneda     = _MONEDA_MAP.get((a.get("moneda") or "").lower(), "ARS")
            valorizado = float(a.get("valorizado") or 0)
            simbolo    = a.get("simbolo") or "?"
            desc       = (a.get("descripcion") or "").strip()
            variacion  = float(a.get("variacion") or 0)
            tipo_label = _TIPO_MAP.get(a.get("tipo_instrumento") or "", "")
            extra      = (f"  [{tipo_label}]" if tipo_label else "") + (f"  {desc}" if desc else "")

            if moneda == "USD":
                val_usd += valorizado
                log_fn(f"  {simbolo:<10} = U${valorizado:>10,.2f}  ({variacion:+.2f}%){extra}")
            else:
                val_ars += valorizado
                log_fn(f"  {simbolo:<10} = ${valorizado:>12,.0f}  ({variacion:+.2f}%){extra}")

        # Efectivo en cuenta (saldos de liquidación — normalmente ARS)
        for s in estado_cuenta.get("saldos") or []:
            saldo = float(s.get("saldo") or 0)
            if saldo:
                liq = s.get("liquidacion") or "efectivo"
                val_ars += saldo
                log_fn(f"  Efectivo ({liq}): ${saldo:,.0f} ARS")

        log_fn(
            f"Total portafolio: ${val_ars:,.0f} ARS  |  U${val_usd:,.2f} USD"
        )
        return round(val_ars, 2), round(val_usd, 2)

    # ── Operaciones ──────────────────────────────────────────────────────────

    async def _fetch_operaciones(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        dias: int,
        log_fn,
    ) -> list[MovimientoRaw]:
        today = datetime.now(_ART).date()
        desde = today - timedelta(days=dias - 1)
        log_fn(f"Consultando operaciones (últimos {dias} días)…")
        try:
            resp = await client.get(
                f"{_BASE}/api/v2/operaciones",
                headers=headers,
                params={
                    "estado":     "terminadas",
                    "fechaDesde": f"{desde}T00:00:00",
                    "fechaHasta": f"{today}T23:59:59",
                    "tipo":       "todos",
                },
            )
            resp.raise_for_status()
            ops = resp.json() or []
        except Exception as exc:
            log_fn(f"Operaciones no disponibles: {exc}")
            return []

        movimientos = [m for op in ops if (m := self._op_to_movimiento(op))]
        log_fn(f"Operaciones importadas: {len(movimientos)}")
        return movimientos

    def _op_to_movimiento(self, op: dict) -> Optional[MovimientoRaw]:
        try:
            tipo   = (op.get("tipo") or "").strip()
            estado = (op.get("estado") or "").strip().lower()
            if estado != "terminada":
                return None

            fecha_str = (op.get("fechaOrden") or "")[:10]
            if len(fecha_str) < 10:
                return None

            monto_raw = float(op.get("monto") or 0)
            if monto_raw <= 0:
                return None

            moneda   = _MONEDA_MAP.get((op.get("moneda") or "").lower(), "ARS")
            tipo_l   = tipo.lower()
            sign     = -1 if any(k in tipo_l for k in _SIGN_INGRESO) else +1

            instrumento = op.get("instrumento") or {}
            simbolo     = (instrumento.get("simbolo") or "").strip()
            nombre_inst = (instrumento.get("descripcion") or "").strip()
            parts       = [tipo] + ([simbolo] if simbolo else [])
            if nombre_inst and nombre_inst != simbolo:
                parts.append(nombre_inst)

            return MovimientoRaw(
                fuente      = self.fuente,
                fecha       = fecha_str,
                descripcion = " — ".join(parts),
                monto       = round(monto_raw * sign, 2),
                moneda      = moneda,
                raw_data    = {
                    "numero":   op.get("numero"),
                    "tipo":     tipo,
                    "simbolo":  simbolo,
                    "cantidad": op.get("cantidad"),
                    "precio":   op.get("precio"),
                },
            )
        except Exception as exc:
            logger.warning("[iol] Error convirtiendo op %s: %s", op.get("numero"), exc)
            return None

    # ── Stubs Selenium (nunca se invocan) ─────────────────────────────────────

    def check_session(self, driver) -> bool:
        return False

    def do_login(self, driver, config: dict) -> None:
        pass

    def scrape(self, driver, config: dict) -> ScraperResult:
        return ScraperResult(fuente=self.fuente)

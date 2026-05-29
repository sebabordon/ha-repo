"""
Scraper InvertirOnline — API REST.

No usa Selenium. Autenticación OAuth2 (grant_type=password) con refresh automático.

Funcionalidad:
  1. Autenticar → access_token + refresh_token (TTL 1 hora, refresh automático)
  2. GET /api/v2/estadocuenta → saldo_ars y saldo_usd por cuenta (cash + títulos)
  3. GET /api/v2/portafolio/{pais} → log detallado de cada tenencia
  4. GET /api/v2/operaciones → importar compras/ventas como movimientos (opcional)

El estadocuenta es la fuente de saldos: cada cuenta tiene `total` = cash + títulos
valorizados, separado por moneda. El portafolio se usa solo para el log detallado.
"""

import json as _json
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

# Tipos de operación que son ingresos (signo negativo en nuestra convención)
_SIGN_INGRESO = ("venta", "cobro", "acreditaci", "dividendo", "renta")


def _to_moneda(raw) -> str:
    """
    Convierte el campo `moneda` de IOL a "ARS" o "USD".
    Acepta int (0=ARS, 1=USD), string en cualquier case
    ("peso_Argentino", "dolar_Estadounidense", "peso_argentino", etc.)
    """
    if raw is None:
        return "ARS"
    if isinstance(raw, int):
        return "USD" if raw == 1 else "ARS"
    s = str(raw).lower()
    if "dolar" in s or "dollar" in s or s == "1":
        return "USD"
    return "ARS"


def _tipo_label(raw: str) -> str:
    """
    Convierte tipo de instrumento IOL a etiqueta corta.
    Acepta snake_case ("fondos_comunes_de_inversion") o PascalCase ("FondoComun").
    """
    if not raw:
        return ""
    t = raw.lower()
    if "cedear" in t:                           return "CEDEAR"
    if "fondo" in t or "fci" in t:             return "FCI"
    if "accion" in t or "acción" in t:         return "Acción"
    if "titulo" in t or "bono" in t:           return "Bono"
    if "obligacion" in t or "obligación" in t: return "ON"
    if "caucion" in t or "caución" in t:       return "Caución"
    if "opcion" in t or "opción" in t:         return "Opción"
    if "futuro" in t:                           return "Futuro"
    return ""


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
                data = _json.load(f)
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
                _json.dump({
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

                # 1. Estado de cuenta → saldos por moneda
                _l("Consultando estado de cuenta…")
                resp_ec = await client.get(f"{_BASE}/api/v2/estadocuenta", headers=hdrs)
                if resp_ec.status_code == 401:
                    self.clear_session()
                    raise ValueError(
                        "Token inválido (401) — sesión eliminada, el próximo run hará re-login"
                    )
                resp_ec.raise_for_status()
                saldo_ars, saldo_usd = self._process_estadocuenta(resp_ec.json(), _l)

                # 2. Portafolio → log de tenencias individuales
                _l(f"Consultando tenencias ({_PAIS})…")
                resp_pf = await client.get(
                    f"{_BASE}/api/v2/portafolio/{_PAIS}", headers=hdrs
                )
                if resp_pf.status_code == 200:
                    self._log_holdings(resp_pf.json(), _l)
                else:
                    _l(f"Portafolio no disponible: HTTP {resp_pf.status_code}")

                # 3. Operaciones (opcional)
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

    # ── Estado de cuenta (saldos) ──────────────────────────────────────────────

    def _process_estadocuenta(self, ec: dict, log_fn) -> tuple[float, float]:
        """
        Extrae saldo_ars y saldo_usd de /api/v2/estadocuenta.

        Cada cuenta en ec["cuentas"] tiene:
          - moneda: "peso_Argentino" | "dolar_Estadounidense"
          - total:  cash + títulos valorizados (lo que queremos como saldo)
        """
        cuentas = ec.get("cuentas") or []
        log_fn(f"[debug] estadocuenta keys: {list(ec.keys())}  cuentas: {len(cuentas)}")

        val_ars = 0.0
        val_usd = 0.0

        for c in cuentas:
            moneda  = _to_moneda(c.get("moneda"))
            total   = float(c.get("total") or 0)
            saldo   = float(c.get("saldo") or 0)          # cash
            titulos = float(c.get("titulosValorizados") or 0)
            tipo    = (c.get("tipo") or "").replace("_", " ")
            estado  = c.get("estado") or ""

            if moneda == "USD":
                val_usd += total
                log_fn(
                    f"  Cuenta USD ({tipo}): cash U${saldo:,.2f}"
                    f" + títulos U${titulos:,.2f} = U${total:,.2f}  [{estado}]"
                )
            else:
                val_ars += total
                log_fn(
                    f"  Cuenta ARS ({tipo}): cash ${saldo:,.0f}"
                    f" + títulos ${titulos:,.0f} = ${total:,.0f}  [{estado}]"
                )

        log_fn(f"Total: ${val_ars:,.0f} ARS  |  U${val_usd:,.2f} USD")
        return round(val_ars, 2), round(val_usd, 2)

    # ── Portafolio (log de tenencias) ──────────────────────────────────────────

    def _log_holdings(self, raw: object, log_fn) -> None:
        """
        Loguea las tenencias individuales del portafolio.
        No modifica saldos — es solo para visibilidad en el log del run.
        """
        # La API puede devolver dict con "activos" o array directo
        if isinstance(raw, list):
            activos = raw
        else:
            root_keys = list(raw.keys()) if isinstance(raw, dict) else "?"
            log_fn(f"[debug] portafolio keys: {root_keys}")
            activos = raw.get("activos") or []

        if not activos:
            log_fn("Sin tenencias individuales en portafolio.")
            return

        log_fn(f"Tenencias ({len(activos)}):")
        if activos:
            log_fn(f"[debug] activo[0]: {_json.dumps(activos[0])[:500]}")

        for a in activos:
            titulo     = a.get("titulo") or {}
            simbolo    = (titulo.get("simbolo") or a.get("simbolo") or "?").strip()
            desc       = (titulo.get("descripcion") or a.get("descripcion") or "").strip()
            tipo_raw   = titulo.get("tipo") or a.get("tipo_instrumento") or ""
            moneda     = _to_moneda(a.get("moneda") or titulo.get("moneda"))
            valorizado = float(a.get("valorizado") or 0)
            variacion  = float(a.get("variacion") or a.get("variacionDiaria") or 0)
            label      = _tipo_label(tipo_raw)
            extra      = (f"  [{label}]" if label else "") + (f"  {desc}" if desc else "")

            if moneda == "USD":
                log_fn(f"  {simbolo:<12} U${valorizado:>10,.2f}  ({variacion:+.2f}%){extra}")
            else:
                log_fn(f"  {simbolo:<12}  ${valorizado:>12,.0f}  ({variacion:+.2f}%){extra}")

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

            moneda = _to_moneda(op.get("moneda"))
            tipo_l = tipo.lower()
            sign   = -1 if any(k in tipo_l for k in _SIGN_INGRESO) else +1

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

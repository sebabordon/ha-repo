"""
Clase base para todos los scrapers de bancos.

Flujo de cada run():
  1. Cargar session de /data/sessions/{fuente}.json (si existe)
  2. Llamar check_session() → si falla, llamar do_login()
  3. Llamar scrape() para obtener movimientos y saldos
  4. Guardar session actualizada en disco
  5. Registrar resultado en scraper_status

Las subclases implementan check_session / do_login / scrape.
"""

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR     = os.environ.get("DATA_DIR", "/data")
_SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")

# User-agent genérico que no levanta sospechas en portales bancarios
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── Tipos de datos ─────────────────────────────────────────────────────────────

@dataclass
class MovimientoRaw:
    fuente:        str
    fecha:         str            # ISO YYYY-MM-DD
    descripcion:   str
    monto:         float          # positivo = egreso (igual que gastos)
    moneda:        str = "ARS"
    fecha_proceso: Optional[str] = None
    tarjeta:       Optional[str] = None   # etiqueta libre, ej. "Platinum Credit"
    raw_data:      Optional[dict] = None  # datos originales del scraper (debug)

    def to_dict(self) -> dict:
        return {
            "fuente":        self.fuente,
            "fecha":         self.fecha,
            "descripcion":   self.descripcion,
            "monto":         self.monto,
            "moneda":        self.moneda,
            "fecha_proceso": self.fecha_proceso,
            "tarjeta":       self.tarjeta,
            "raw_data":      self.raw_data,
        }


@dataclass
class ScraperResult:
    fuente:          str
    movimientos:     list[MovimientoRaw] = field(default_factory=list)
    # saldos: {fuente_producto: {"saldo_ars": float, "saldo_usd": float}}
    # ej. {"bbva_mc": {"saldo_ars": 45000.0}, "bbva_cuenta": {"saldo_ars": 120000.0}}
    saldos:          dict = field(default_factory=dict)
    error:           Optional[str] = None
    session_expired: bool = False


# ── Clase base ─────────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers bancarios.

    Subclases deben definir:
      fuente: str   — identificador primario (usado para el archivo de sesión)
      nombre: str   — nombre legible para logs y UI
    """

    fuente: str = ""
    nombre: str = ""

    def __init__(self):
        os.makedirs(_SESSIONS_DIR, exist_ok=True)

    @property
    def session_path(self) -> str:
        return os.path.join(_SESSIONS_DIR, f"{self.fuente}.json")

    def _has_session(self) -> bool:
        return os.path.exists(self.session_path)

    def clear_session(self) -> None:
        """Elimina la sesión guardada. Úsalo cuando el banco invalida la cookie."""
        if self._has_session():
            os.remove(self.session_path)
            logger.info("[%s] Sesión eliminada.", self.fuente)

    # ── Entrada principal ──────────────────────────────────────────────────────

    async def run(self, config: dict) -> ScraperResult:
        """
        Punto de entrada del scheduler.
        Maneja el ciclo completo: sesión → login → scraping → persistencia.
        """
        from scrapers_db import upsert_scraper_status

        now_iso = datetime.utcnow().isoformat()
        upsert_scraper_status(self.fuente, estado="running", ultimo_run=now_iso)

        try:
            result = await self._run_internal(config)
        except Exception as exc:
            logger.exception("[%s] Error inesperado: %s", self.fuente, exc)
            result = ScraperResult(fuente=self.fuente, error=str(exc))

        # Actualizar estado final
        if result.error:
            estado = "session_expired" if result.session_expired else "error"
            upsert_scraper_status(
                self.fuente,
                estado=estado,
                error_msg=result.error,
            )
        else:
            upsert_scraper_status(
                self.fuente,
                estado="ok",
                ultimo_ok=now_iso,
                error_msg=None,
            )
            # Actualizar saldos en la tabla cuentas
            self._persist_saldos(result.saldos)

        return result

    async def _run_internal(self, config: dict) -> ScraperResult:
        from playwright.async_api import async_playwright

        chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")

        async with async_playwright() as p:
            launch_opts: dict = {"headless": True, "args": ["--no-sandbox"]}
            if chromium_path:
                launch_opts["executable_path"] = chromium_path

            browser = await p.chromium.launch(**launch_opts)

            # Intentar restaurar sesión desde disco
            context_opts: dict = {
                "viewport":   {"width": 1280, "height": 800},
                "user_agent": _UA,
            }
            if self._has_session():
                context_opts["storage_state"] = self.session_path

            context = await browser.new_context(**context_opts)
            page    = await context.new_page()

            try:
                # Validar o hacer login
                logged_in = self._has_session() and await self.check_session(page)
                if not logged_in:
                    logger.info("[%s] Sesión inválida o inexistente — iniciando login…", self.fuente)
                    await self.do_login(page, config)

                result = await self.scrape(page, config)

                # Persistir sesión actualizada
                await context.storage_state(path=self.session_path)
                logger.info(
                    "[%s] OK — %d movimientos, saldos: %s",
                    self.fuente, len(result.movimientos), result.saldos,
                )
                return result

            finally:
                await context.close()
                await browser.close()

    # ── Persistencia de saldos ─────────────────────────────────────────────────

    @staticmethod
    def _persist_saldos(saldos: dict) -> None:
        """
        Actualiza cuentas.saldo / saldo_usd para cada fuente con saldo scrapeado.
        saldos = {fuente: {"saldo_ars": float, "saldo_usd": float}}
        """
        try:
            from scrapers_db import _conn
            with _conn() as conn:
                today = datetime.now().strftime("%Y-%m-%d")
                for fuente, vals in saldos.items():
                    if "saldo_ars" in vals:
                        conn.execute(
                            "UPDATE cuentas SET saldo=?, fecha_actualizacion=? "
                            "WHERE fuente=? AND auto_saldo=1",
                            (vals["saldo_ars"], today, fuente),
                        )
                    if "saldo_usd" in vals:
                        conn.execute(
                            "UPDATE cuentas SET saldo_usd=?, fecha_actualizacion=? "
                            "WHERE fuente=? AND auto_saldo=1",
                            (vals["saldo_usd"], today, fuente),
                        )
        except Exception as exc:
            logger.error("Error al persistir saldos: %s", exc)

    # ── Métodos abstractos ─────────────────────────────────────────────────────

    @abstractmethod
    async def check_session(self, page) -> bool:
        """
        Navega a una URL protegida y devuelve True si la sesión sigue activa.
        Debe resolver en < 15 segundos.
        """

    @abstractmethod
    async def do_login(self, page, config: dict) -> None:
        """
        Login completo con las credenciales del config.
        Lanza excepción si falla.
        """

    @abstractmethod
    async def scrape(self, page, config: dict) -> ScraperResult:
        """
        Con sesión activa, raspa todos los productos del banco.
        Devuelve movimientos y saldos.
        """

    # ── Helpers compartidos ────────────────────────────────────────────────────

    @staticmethod
    def parse_amount(text: str) -> float:
        """
        Parsea un importe en formato argentino a float.
        Positivo = egreso, negativo = crédito/ingreso.

        Ejemplos:
          "1.234,56"   → 1234.56
          "$ 1.234,56" → 1234.56
          "-100,00"    → -100.0
          "1234.56"    → 1234.56  (formato US, sin puntos miles)
          "CR 500,00"  → -500.0   (CR/Cr = crédito)
        """
        if not text:
            return 0.0
        t = text.strip()

        # Crédito explícito (CR, Cr, cr)
        is_credit = bool(re.search(r"\bCR\b", t, re.IGNORECASE))

        # Remover símbolos de moneda y etiquetas
        t = re.sub(r"(CR|USD|US\$|\$|ARS)", "", t, flags=re.IGNORECASE).strip()

        # Signo
        negative = t.startswith("-")
        t = t.lstrip("+-").strip()

        # Detectar formato: si tiene coma Y punto, ver cuál va último
        has_dot   = "." in t
        has_comma = "," in t

        if has_dot and has_comma:
            if t.rfind(",") > t.rfind("."):
                # 1.234,56 → formato AR
                t = t.replace(".", "").replace(",", ".")
            else:
                # 1,234.56 → formato US
                t = t.replace(",", "")
        elif has_comma:
            # 1234,56 → decimal con coma
            t = t.replace(",", ".")
        # else: ya es float puro

        try:
            val = float(t)
        except ValueError:
            return 0.0

        if negative or is_credit:
            val = -val
        return val

    @staticmethod
    def parse_date_ar(text: str) -> Optional[str]:
        """
        Parsea fechas en formato DD/MM/YYYY o DD/MM/YY a ISO YYYY-MM-DD.
        Devuelve None si no puede parsear.
        """
        if not text:
            return None
        text = text.strip()
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", text)
        if not m:
            return None
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = "20" + year
        try:
            from datetime import date
            d = date(int(year), int(month), int(day))
            return d.isoformat()
        except ValueError:
            return None

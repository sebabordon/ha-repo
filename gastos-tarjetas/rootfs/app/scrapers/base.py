"""
Clase base para scrapers bancarios — usa Selenium + Chromium del sistema.

Por qué Selenium en lugar de Playwright:
  Playwright solo publica wheels para manylinux (glibc). La imagen base de HA
  usa Alpine Linux (musl libc), que es incompatible con manylinux. Selenium es
  py3-none-any (pure Python); el browser lo provee chromium-chromedriver via apk.

Flujo de cada run():
  1. Crear WebDriver con Chromium headless
  2. Restaurar sesión (cookies + localStorage) desde /data/sessions/{fuente}.json
  3. check_session() → si falla, do_login()
  4. scrape() para obtener movimientos y saldos
  5. Guardar sesión actualizada
  6. Registrar resultado en scraper_status

Selenium es síncrono; run() envuelve _run_sync() en un thread pool para mantener
la interfaz async del scheduler sin bloquear el event loop de FastAPI.
"""

import asyncio
import contextvars
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _sessions_dir() -> str:
    """
    Dir de sesiones de browser del scraper, **por usuario** — resuelto en runtime
    desde el ContextVar de userctx.  Antes era la constante global
    `/data/sessions`, lo que hacía que dos usuarios con el mismo banco
    compartieran/pisaran las cookies de sesión bancaria (fuga entre usuarios).
    """
    try:
        from userctx import get_data_dir
        base = get_data_dir()
    except Exception:
        base = _DATA_DIR
    return os.path.join(base, "sessions")

# Binarios del sistema (seteados como ENV en el Dockerfile)
_CHROMIUM_BIN    = os.environ.get("CHROMIUM_BIN",    "/usr/bin/chromium-browser")
_CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
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
    tarjeta:       Optional[str] = None
    raw_data:      Optional[dict] = None

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
    saldos:          dict = field(default_factory=dict)
    error:           Optional[str] = None
    session_expired: bool = False
    # Líneas de diagnóstico legibles — se guardan en scraper_status.last_log
    log_lines:       list[str] = field(default_factory=list)


# ── Clase base ─────────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers bancarios.

    Subclases deben definir:
      fuente: str           — identificador (usado para el archivo de sesión)
      nombre: str           — nombre legible
      login_origin: str     — dominio raíz del banco (para restaurar cookies)

    Opcionales:
      session_ttl_seconds: int|None — si la sesión guardada es más vieja que
          este TTL (en segundos), `_has_session()` la considera inválida y
          devuelve False (forzando re-login).  None = sin expiración (default).
          Útil para bancos con sesiones cortas (ej. BBVA expira en 5 min).
    """

    fuente:              str = ""
    nombre:              str = ""
    login_origin:        str = ""   # ej. "https://www.bbva.com.ar"
    session_ttl_seconds: Optional[int] = None
    # Si False, la sesión NO se guarda al terminar el run.  Útil para bancos con
    # timeouts de sesión muy cortos (ej. BBVA 5 min) donde guardar cookies stale
    # solo genera redirects a /desconexion.html en el siguiente run.
    save_session:        bool = True
    # Si False, Chromium corre NO-headless (headful) bajo el display virtual Xvfb
    # (DISPLAY=:99, ver run.sh).  Necesario para bancos cuyo anti-bot (InAuth,
    # Akamai) detecta y bloquea headless — ej. AMEX.  Default True (headless).
    headless:            bool = True

    def __init__(self):
        os.makedirs(_sessions_dir(), exist_ok=True)

    @property
    def session_path(self) -> str:
        return os.path.join(_sessions_dir(), f"{self.fuente}.json")

    def _has_session(self) -> bool:
        if not os.path.exists(self.session_path):
            return False
        # TTL check: si la sesión es más vieja que session_ttl_seconds, descartarla
        # sin intentar usarla (evita el ciclo restore→check_session(falla)→login con
        # cookies stale que disparaba el redirect a /desconexion.html en BBVA).
        if self.session_ttl_seconds is not None:
            try:
                age = time.time() - os.path.getmtime(self.session_path)
                if age > self.session_ttl_seconds:
                    logger.info(
                        "[%s] Sesión guardada hace %.0fs (TTL=%ds) — descartando, se hará login.",
                        self.fuente, age, self.session_ttl_seconds,
                    )
                    return False
            except Exception:
                pass   # si stat falla, devolver True y dejar que check_session decida
        return True

    def clear_session(self) -> None:
        if self._has_session():
            os.remove(self.session_path)
            logger.info("[%s] Sesión eliminada.", self.fuente)

    # ── WebDriver factory ─────────────────────────────────────────────────────

    def _create_driver(self):
        """Crea y devuelve un WebDriver configurado con Chromium headless."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        else:
            # Headful bajo Xvfb: el anti-bot (InAuth de AMEX) detecta headless.
            # Requiere DISPLAY=:99 (Xvfb, ver run.sh). Sin headless, --no-sandbox
            # y el resto de flags siguen aplicando.
            logger.info("[%s] Chromium en modo headful (Xvfb DISPLAY=%s)",
                        self.fuente, os.environ.get("DISPLAY", "(no seteado)"))
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument(f"--user-agent={_UA}")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        if os.path.exists(_CHROMIUM_BIN):
            opts.binary_location = _CHROMIUM_BIN

        service = Service(
            executable_path=_CHROMEDRIVER_BIN
            if os.path.exists(_CHROMEDRIVER_BIN)
            else "chromedriver"
        )
        driver = webdriver.Chrome(service=service, options=opts)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(0)   # usamos waits explícitos

        # ── Parches de fingerprint via CDP ─────────────────────────────────────
        # Akamai BotManager detecta automatización verificando propiedades del
        # browser que difieren entre headless y un browser real.  Estas overrides
        # se inyectan ANTES de que cargue cualquier página.
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    // 1. navigator.webdriver → undefined (ya cubierto por --disable-blink-features
                    //    pero lo reforzamos por si acaso)
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined, configurable: true
                    });
                    // 2. window.chrome — ausente en headless; Akamai lo verifica
                    if (!window.chrome) {
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                    }
                    // 3. navigator.plugins — headless tiene 0; simulamos algunos
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            var p = [
                                {name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'},
                                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
                                {name:'Native Client',     filename:'internal-nacl-plugin',  description:''}
                            ];
                            p.__proto__ = PluginArray.prototype;
                            return p;
                        }
                    });
                    // 4. Notification.permission — headless devuelve 'denied'; cambiamos a 'default'
                    try {
                        Object.defineProperty(Notification, 'permission', {
                            get: () => 'default'
                        });
                    } catch(e) {}
                    // 5. navigator.languages — idioma de Argentina
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['es-AR', 'es', 'en-US', 'en']
                    });
                    // 6. navigator.platform — Windows (coherente con el User-Agent)
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32'
                    });
                """
            })
        except Exception as _cdp_err:
            pass   # si la versión de chromedriver no soporta CDP, ignoramos

        return driver

    # ── Sesión (cookies + localStorage) ──────────────────────────────────────

    def _save_session(self, driver) -> None:
        """Serializa cookies y localStorage a disco."""
        try:
            cookies = driver.get_cookies()
            try:
                ls = driver.execute_script(
                    "try { return Object.fromEntries(Object.entries(localStorage)); }"
                    " catch(e) { return {}; }"
                ) or {}
            except Exception:
                ls = {}
            state = {"cookies": cookies, "localStorage": ls}
            with open(self.session_path, "w") as f:
                json.dump(state, f)
            logger.info("[%s] Sesión guardada (%d cookies).", self.fuente, len(cookies))
        except Exception as exc:
            logger.error("[%s] Error guardando sesión: %s", self.fuente, exc)

    def _restore_session(self, driver) -> None:
        """
        Carga la sesión guardada en el driver.
        Hay que estar en el dominio correcto antes de agregar cookies,
        por eso primero navegamos a login_origin.
        """
        if not self._has_session():
            return
        try:
            with open(self.session_path) as f:
                state = json.load(f)

            driver.get(self.login_origin)
            time.sleep(1)

            for cookie in state.get("cookies", []):
                # Selenium no acepta cookies con el campo 'sameSite' inválido
                cookie.pop("sameSite", None)
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass  # cookie de subdominio o formato inválido — no es fatal

            ls = state.get("localStorage", {})
            if ls:
                driver.execute_script(
                    "Object.entries(arguments[0]).forEach(([k,v]) => {"
                    "  try { localStorage.setItem(k, v); } catch(e) {}"
                    "});",
                    ls,
                )
            logger.debug("[%s] Sesión restaurada.", self.fuente)
        except Exception as exc:
            logger.warning("[%s] Error restaurando sesión: %s", self.fuente, exc)

    # ── Entrada principal (async → thread pool) ───────────────────────────────

    async def run(self, config: dict) -> ScraperResult:
        """
        Punto de entrada async del scheduler.
        Selenium es síncrono; lo corremos en un thread pool para no bloquear
        el event loop de FastAPI/APScheduler.
        """
        from scrapers_db import upsert_scraper_status

        now_iso = datetime.utcnow().isoformat()
        upsert_scraper_status(self.fuente, estado="running", ultimo_run=now_iso)

        loop   = asyncio.get_event_loop()
        ctx    = contextvars.copy_context()
        result = await loop.run_in_executor(None, ctx.run, self._run_sync, config)

        last_log = "\n".join(result.log_lines) if result.log_lines else None

        if result.error:
            estado = "session_expired" if result.session_expired else "error"
            upsert_scraper_status(
                self.fuente, estado=estado, error_msg=result.error, last_log=last_log,
            )
        else:
            upsert_scraper_status(
                self.fuente,
                estado="ok",
                ultimo_ok=datetime.utcnow().isoformat(),
                error_msg=None,
                last_log=last_log,
            )
            self._persist_saldos(result.saldos)

        return result

    def _run_sync(self, config: dict) -> ScraperResult:
        """Núcleo síncrono: crea driver, restaura sesión, loguea si es necesario, scrapea."""
        driver = None
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[%s] %s", self.fuente, msg)
            log.append(msg)

        try:
            _log("Iniciando WebDriver…")
            driver = self._create_driver()

            # Si este scraper no persiste sesión, borrar cualquier archivo stale
            # antes de intentar nada — así no se restauran cookies vencidas.
            if not self.save_session:
                self.clear_session()

            # Intentar restaurar sesión y verificar validez
            has_session = self._has_session()
            _log(f"Sesión guardada en disco: {'sí' if has_session else 'no'}")

            if has_session:
                _log("Restaurando cookies desde sesión guardada…")
                self._restore_session(driver)
                _log("Verificando validez de sesión…")
                session_ok = self.check_session(driver)
                _log(f"Sesión válida: {'sí' if session_ok else 'no — se hará login'}")
            else:
                session_ok = False
                _log("Sin sesión previa — se hará login")

            if not session_ok:
                _log("Iniciando login…")
                self.do_login(driver, config)
                _log("Login completado")

            _log("Iniciando scraping de movimientos…")
            result = self.scrape(driver, config)
            result.log_lines = log + result.log_lines

            # Persistir sesión actualizada (si el scraper lo permite)
            if self.save_session:
                self._save_session(driver)
                _log(f"Sesión guardada. Movimientos encontrados: {len(result.movimientos)}")
            else:
                self.clear_session()   # borrar cualquier sesión stale que pudiera existir
                _log(f"Sesión no persistida (save_session=False). Movimientos encontrados: {len(result.movimientos)}")

            logger.info(
                "[%s] OK — %d movimientos, saldos: %s",
                self.fuente, len(result.movimientos), result.saldos,
            )
            return result

        except Exception as exc:
            logger.exception("[%s] Error en scraper: %s", self.fuente, exc)
            log.append(f"ERROR: {exc}")
            return ScraperResult(fuente=self.fuente, error=str(exc), log_lines=log)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ── Persistencia de saldos ────────────────────────────────────────────────

    @staticmethod
    def _persist_saldos(saldos: dict) -> None:
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

    # ── Helpers multi-instancia (v0.4.0+) ─────────────────────────────────────

    @staticmethod
    def _fuente_for_product(config: dict, product_key: str,
                            default_fuente: str) -> str:
        """
        Devuelve la `fuente` que el scraper debe emitir para un producto dado.

        Resuelve a partir de `config["__cuentas__"]` (lista de cuentas mapeadas
        por el scheduler).  Para scrapers single-product (AMEX, Galicia, MP),
        `product_key="main"` matchea cualquier cuenta sin product_key específico.

        Si no hay match (o `__cuentas__` no viene en el config — modo legacy
        standalone), devuelve `default_fuente` (la fuente clásica hardcoded
        del scraper, ej. "amex" para AMEX, "mercadopago" para MP).
        """
        cuentas = config.get("__cuentas__") or []
        if not cuentas:
            return default_fuente
        # Match exacto por product_key
        for c in cuentas:
            if (c.get("product_key") or "").upper() == (product_key or "").upper():
                return c.get("fuente") or default_fuente
        # Fallback: si single-product, usar la primera cuenta mapeada
        if len(cuentas) == 1 and (product_key or "").lower() == "main":
            return cuentas[0].get("fuente") or default_fuente
        return default_fuente

    @staticmethod
    def _resumenes_cutoff(config: dict):
        """
        Fecha de corte (date) para el backfill de resúmenes PDF, según el config
        'resumenes_meses' (default 1, clamp 1..24). Se importan los resúmenes con
        fecha de cierre >= cutoff. El cutoff es el día 1 del mes N meses atrás, para
        abarcar el mes completo del límite.
        """
        from datetime import date
        try:
            meses = int(str(config.get("resumenes_meses") or "1").strip())
        except (TypeError, ValueError):
            meses = 1
        meses = max(1, min(meses, 24))
        today = date.today()
        m, y = today.month - meses, today.year
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, 1)

    # ── Métodos abstractos ────────────────────────────────────────────────────

    @abstractmethod
    def check_session(self, driver) -> bool:
        """
        Navega a una URL protegida y devuelve True si la sesión sigue activa.
        Debe ser síncrono (no async). Timeout razonable: ~15 s.
        """

    @abstractmethod
    def do_login(self, driver, config: dict) -> None:
        """Login completo con credenciales del config. Lanza excepción si falla."""

    @abstractmethod
    def scrape(self, driver, config: dict) -> ScraperResult:
        """Con sesión activa, raspa todos los productos. Devuelve movimientos y saldos."""

    # ── Helpers de Selenium ───────────────────────────────────────────────────

    @staticmethod
    def wait_for(driver, css_selector: str, timeout: int = 15):
        """Espera a que aparezca un elemento CSS. Lanza TimeoutException si no aparece."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )

    @staticmethod
    def wait_visible(driver, css_selector: str, timeout: int = 15):
        """
        Espera y devuelve el PRIMER elemento visible+habilitado que matchea el
        selector. A diferencia de wait_for (que usa presence y devuelve el primer
        match del DOM), evita devolver duplicados OCULTOS — ej. cuando coexisten
        un form legacy y uno de SPA con el mismo campo — que al interactuar dan
        'element not interactable'. Lanza TimeoutException si ninguno es visible.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        def first_visible(d):
            for el in d.find_elements(By.CSS_SELECTOR, css_selector):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    pass
            return False

        return WebDriverWait(driver, timeout).until(first_visible)

    @staticmethod
    def wait_for_any(driver, selectors: list[str], timeout: int = 15):
        """
        Espera a que aparezca CUALQUIERA de los selectores CSS dados.
        Devuelve el texto del selector que matcheó primero.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        combined = ", ".join(selectors)

        def any_present(d):
            for sel in selectors:
                try:
                    el = d.find_element(By.CSS_SELECTOR, sel)
                    if el:
                        return sel
                except Exception:
                    pass
            return False

        return WebDriverWait(driver, timeout).until(any_present)

    @staticmethod
    def find(driver, css_selector: str):
        """Busca un elemento CSS. Devuelve el elemento o None si no existe."""
        from selenium.webdriver.common.by import By
        try:
            return driver.find_element(By.CSS_SELECTOR, css_selector)
        except Exception:
            return None

    @staticmethod
    def find_all(driver, css_selector: str) -> list:
        """Devuelve todos los elementos que matchean el selector CSS."""
        from selenium.webdriver.common.by import By
        try:
            return driver.find_elements(By.CSS_SELECTOR, css_selector)
        except Exception:
            return []

    # ── Helpers de parsing ────────────────────────────────────────────────────

    @staticmethod
    def parse_amount(text: str) -> float:
        """
        Parsea importe en formato argentino a float.
        Positivo = egreso, negativo = crédito/ingreso.

        Ejemplos:
          "1.234,56"   → 1234.56
          "$ 1.234,56" → 1234.56
          "-100,00"    → -100.0
          "CR 500,00"  → -500.0
        """
        if not text:
            return 0.0
        t = text.strip()
        is_credit = bool(re.search(r"\bCR\b", t, re.IGNORECASE))
        t = re.sub(r"(CR|USD|US\$|\$|ARS)", "", t, flags=re.IGNORECASE).strip()
        negative = t.startswith("-")
        t = t.lstrip("+-").strip()
        has_dot   = "." in t
        has_comma = "," in t
        if has_dot and has_comma:
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                t = t.replace(",", "")
        elif has_comma:
            t = t.replace(",", ".")
        try:
            val = float(t)
        except ValueError:
            return 0.0
        if negative or is_credit:
            val = -val
        return val

    @staticmethod
    def parse_date_ar(text: str) -> Optional[str]:
        """Parsea DD/MM/YYYY o DD/MM/YY a ISO YYYY-MM-DD. Devuelve None si falla."""
        if not text:
            return None
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", text.strip())
        if not m:
            return None
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = "20" + year
        try:
            from datetime import date
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return None

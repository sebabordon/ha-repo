"""
Scraper Banco Galicia — Selenium.

TOTP inicial: el primer login pide un código de 6 dígitos (mail o app).
Con "recordar este dispositivo" activo, la sesión dura semanas.
El flujo interactivo de setup usa threading.Event para pasar el código
desde el endpoint HTTP al thread que tiene el browser abierto.
"""

import logging
import threading
import time
import uuid

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL  = "https://www.bancogalicia.com.ar/banca-en-linea/"
_DASHBOARD  = "https://www.bancogalicia.com.ar/banca-en-linea/home"

# Estado global para setups interactivos de TOTP en curso
# {request_id: {"event": threading.Event, "code": str|None, "status": str, "error": str|None}}
_pending_totp: dict[str, dict] = {}


class GaliciaScraper(BaseScraper):
    fuente       = "galicia"
    nombre       = "Banco Galicia"
    login_origin = "https://www.bancogalicia.com.ar"

    def check_session(self, driver) -> bool:
        try:
            driver.get(_DASHBOARD)
            time.sleep(3)
            # TODO: selector de elemento que solo aparece logueado
            el = self.find(driver,
                ".user-name, [data-testid='user-name'], "
                ".home-dashboard, #dashboardContent"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[galicia] check_session: %s", exc)
            return False

    def do_login(self, driver, config: dict) -> None:
        """
        Login automático. Si aparece pantalla de TOTP sin sesión guardada,
        lanza SessionNeedsTotp para que el scheduler marque session_expired.
        """
        driver.get(_LOGIN_URL)
        time.sleep(2)

        # ── Usuario ────────────────────────────────────────────────────────────
        # TODO: verificar selector
        user_el = self.wait_for(driver,
            "input[name='username'], input[id*='user' i], "
            "input[placeholder*='usuario' i], input[autocomplete='username']",
            timeout=15,
        )
        user_el.clear()
        user_el.send_keys(config["usuario"])
        time.sleep(0.5)

        # ── Contraseña ─────────────────────────────────────────────────────────
        # TODO: verificar selector
        pass_el = self.wait_for(driver, "input[type='password']", timeout=10)
        pass_el.clear()
        pass_el.send_keys(config["password"])
        time.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        # TODO: verificar selector
        submit = self.wait_for(driver,
            "button[type='submit'], button.btn-ingresar",
            timeout=10,
        )
        submit.click()

        # Esperar dashboard O pantalla de TOTP
        # TODO: ajustar selectores de ambos estados
        matched = self.wait_for_any(driver, [
            ".home-dashboard, #dashboardContent",
            "input[maxlength='6'], .otp-input, #otpCode",
        ], timeout=30)

        # Si llegamos a la pantalla de TOTP → la sesión automática no puede continuar
        # TODO: ajustar selector de la pantalla de TOTP
        if self.find(driver, "input[maxlength='6'], .otp-input, #otpCode"):
            raise _SessionNeedsTotp(
                "Galicia requiere TOTP. Usá 'Configurar sesión Galicia' en la UI del add-on."
            )

        logger.info("[galicia] Login OK (sin TOTP requerido)")

    def scrape(self, driver, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        try:
            movs, saldo = self._scrape_mastercard(driver)
            movimientos.extend(movs)
            if saldo is not None:
                saldos["galicia_mc"] = {"saldo_ars": saldo}
        except Exception as exc:
            logger.error("[galicia] Error scrapeando MC: %s", exc)

        return ScraperResult(fuente="galicia", movimientos=movimientos, saldos=saldos)

    def _scrape_mastercard(self, driver) -> tuple[list[MovimientoRaw], float | None]:
        """
        TODO: navegar a Galicia Mastercard y extraer movimientos + saldo.

        IMPORTANTE al implementar: los MovimientoRaw deben usar fuente="galicia_mc"
        (no "galicia") para que coincidan con los gastos importados desde PDF
        (parser galicia_mc) y la conciliación funcione correctamente.
        Ejemplo:
            movs.append(MovimientoRaw(fuente="galicia_mc", fecha=..., ...))
        """
        logger.warning("[galicia] _scrape_mastercard — TODO: implementar")
        return [], None

    # ── Flujo interactivo TOTP ────────────────────────────────────────────────

    def start_session_setup(self, config: dict) -> str:
        """
        Inicia el flujo de setup con TOTP en un background thread.
        Devuelve request_id; el browser queda parado esperando el código.
        """
        request_id = str(uuid.uuid4())
        _pending_totp[request_id] = {
            "event":  threading.Event(),
            "code":   None,
            "status": "waiting_totp",
            "error":  None,
        }
        t = threading.Thread(
            target=self._run_totp_setup,
            args=(config, request_id),
            daemon=True,
            name=f"galicia_totp_{request_id[:8]}",
        )
        t.start()
        return request_id

    def submit_totp_code(self, request_id: str, code: str) -> bool:
        """Envía el código TOTP al thread que lo está esperando."""
        entry = _pending_totp.get(request_id)
        if not entry:
            return False
        entry["code"] = code
        entry["event"].set()
        return True

    def get_totp_status(self, request_id: str) -> dict | None:
        entry = _pending_totp.get(request_id)
        if not entry:
            return None
        return {"status": entry["status"], "error": entry["error"]}

    def _run_totp_setup(self, config: dict, request_id: str) -> None:
        """Thread que corre el browser, llega al TOTP y espera el código."""
        from scrapers_db import upsert_scraper_status
        from datetime import datetime

        entry = _pending_totp.get(request_id)
        if not entry:
            return

        driver = None
        try:
            driver = self._create_driver()
            driver.get(_LOGIN_URL)
            time.sleep(2)

            # ── Usuario ────────────────────────────────────────────────────────
            # TODO: mismo selector que do_login
            user_el = self.wait_for(driver,
                "input[name='username'], input[id*='user' i]",
                timeout=15,
            )
            user_el.clear()
            user_el.send_keys(config["usuario"])
            time.sleep(0.5)

            # ── Contraseña ─────────────────────────────────────────────────────
            pass_el = self.wait_for(driver, "input[type='password']", timeout=10)
            pass_el.clear()
            pass_el.send_keys(config["password"])
            time.sleep(0.5)

            submit = self.wait_for(driver,
                "button[type='submit'], button.btn-ingresar",
                timeout=10,
            )
            submit.click()

            # ── Esperar pantalla TOTP ──────────────────────────────────────────
            # TODO: ajustar selector de la pantalla de TOTP
            totp_input = self.wait_for(driver,
                "input[maxlength='6'], .otp-input, #otpCode",
                timeout=30,
            )
            logger.info("[galicia_setup] Pantalla TOTP detectada, esperando código…")
            entry["status"] = "waiting_code"

            # Esperar que el usuario ingrese el código (5 min timeout)
            got_code = entry["event"].wait(timeout=300)
            if not got_code:
                entry["status"] = "timeout"
                entry["error"]  = "Timeout esperando el código TOTP"
                return

            code = entry["code"]
            if not code:
                entry["error"] = "Código vacío"
                return

            # ── Ingresar código ────────────────────────────────────────────────
            totp_input.clear()
            totp_input.send_keys(code)
            time.sleep(0.5)

            # TODO: ¿hay checkbox "recordar este dispositivo"?
            remember = self.find(driver,
                "input[type='checkbox'][name*='remember' i], "
                "input[type='checkbox'][id*='remember' i]"
            )
            if remember:
                try:
                    if not remember.is_selected():
                        remember.click()
                    time.sleep(0.3)
                except Exception:
                    pass

            # TODO: botón de confirmar TOTP
            confirm = self.wait_for(driver,
                "button[type='submit'], button:has-text('Confirmar'), "
                "button.btn-confirmar",
                timeout=10,
            )
            confirm.click()

            # Esperar dashboard post-TOTP
            # TODO: ajustar selector
            self.wait_for(driver,
                ".home-dashboard, #dashboardContent",
                timeout=30,
            )

            # Guardar sesión
            self._save_session(driver)
            entry["status"] = "ok"
            logger.info("[galicia_setup] Sesión configurada OK")

            upsert_scraper_status(
                "galicia",
                estado="ok",
                ultimo_ok=datetime.utcnow().isoformat(),
                error_msg=None,
            )

        except Exception as exc:
            logger.exception("[galicia_setup] Error: %s", exc)
            entry["status"] = "error"
            entry["error"]  = str(exc)
            upsert_scraper_status("galicia", estado="error", error_msg=str(exc))
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            # Limpiar entrada después de 5 min para no acumular
            threading.Timer(300, lambda: _pending_totp.pop(request_id, None)).start()


class _SessionNeedsTotp(Exception):
    """Indica que el login automático requiere TOTP interactivo."""

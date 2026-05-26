"""
Scraper MercadoPago Argentina — Selenium.
"""

import logging
import time

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN    = "https://www.mercadopago.com.ar/hub/login"
_ACTIVITY = "https://www.mercadopago.com.ar/activities"


class MercadoPagoScraper(BaseScraper):
    fuente       = "mercadopago"
    nombre       = "MercadoPago"
    login_origin = "https://www.mercadopago.com.ar"

    def check_session(self, driver) -> bool:
        try:
            driver.get(_ACTIVITY)
            time.sleep(3)
            # TODO: selector de elemento que solo aparece logueado
            el = self.find(driver,
                "[data-testid='navbar-user-avatar'], .nav-user-avatar, "
                "[data-testid='activity-list']"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[mp] check_session: %s", exc)
            return False

    def do_login(self, driver, config: dict) -> None:
        driver.get(_LOGIN)
        time.sleep(2)

        # ── Email / teléfono ────────────────────────────────────────────────────
        # TODO: verificar selector — MP suele usar data-testid
        user_el = self.wait_for(driver,
            "input[data-testid='login-identifier-input'], "
            "input[name='user_id'], input[type='email']",
            timeout=15,
        )
        user_el.clear()
        user_el.send_keys(config["usuario"])
        time.sleep(0.5)

        # TODO: ¿hay botón "Continuar" antes de la contraseña?
        cont = self.find(driver, "button[data-testid='action-next'], button[type='submit']")
        if cont:
            try:
                cont.click()
                time.sleep(2)
            except Exception:
                pass

        # ── Contraseña ──────────────────────────────────────────────────────────
        # TODO: verificar selector
        pass_el = self.wait_for(driver,
            "input[data-testid='password-input'], input[type='password']",
            timeout=10,
        )
        pass_el.clear()
        pass_el.send_keys(config["password"])
        time.sleep(0.5)

        # ── Submit ──────────────────────────────────────────────────────────────
        submit = self.wait_for(driver,
            "button[data-testid='action-confirm'], button[type='submit']",
            timeout=10,
        )
        submit.click()

        # Esperar resultado: dashboard o 2FA
        matched = self.wait_for_any(driver, [
            "[data-testid='activity-list'], .nav-user-avatar",
            "[data-testid='2fa-input'], input[placeholder*='código' i]",
        ], timeout=30)

        # Si aparece 2FA → no podemos continuar automáticamente
        if self.find(driver, "[data-testid='2fa-input'], input[placeholder*='código' i]"):
            raise RuntimeError(
                "MercadoPago requiere 2FA. Deshabilitá el 2FA en la cuenta "
                "o configurá una sesión manualmente."
            )

        logger.info("[mp] Login OK")

    def scrape(self, driver, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        try:
            movs, saldo = self._scrape_cuenta(driver)
            movimientos.extend(movs)
            if saldo is not None:
                saldos["mercadopago"] = {"saldo_ars": saldo}
        except Exception as exc:
            logger.error("[mp] Error scrapeando cuenta: %s", exc)

        return ScraperResult(fuente="mercadopago", movimientos=movimientos, saldos=saldos)

    def _scrape_cuenta(self, driver) -> tuple[list[MovimientoRaw], float | None]:
        """
        TODO: extraer movimientos y saldo de la cuenta MP.

        Pasos típicos:
          1. driver.get(_ACTIVITY)
          2. Leer saldo disponible
          3. Leer filas de movimientos: fecha | descripción | importe
          4. Monto positivo en pantalla = ingreso → negativo en nuestra convención
             Monto negativo en pantalla = egreso → positivo en nuestra convención
             (verificar cómo MP muestra los signos)
        """
        logger.warning("[mp] _scrape_cuenta — TODO: implementar")
        return [], None

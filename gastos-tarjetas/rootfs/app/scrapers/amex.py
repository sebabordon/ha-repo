"""
Scraper AMEX Argentina — Selenium.

Un login → dos tarjetas (Platinum Credit Card + Platinum Card) → fuente 'amex'.
Sin OTP. El campo `tarjeta` en movimientos_raw distingue cuál es cuál.
"""

import logging
import time

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.americanexpress.com/es-ar/account/login"
_ACCOUNT   = "https://www.americanexpress.com/es-ar/account/activity"


class AmexScraper(BaseScraper):
    fuente       = "amex"
    nombre       = "AMEX Argentina"
    login_origin = "https://www.americanexpress.com"

    # Nombres de tarjeta tal como aparecen en el portal AMEX
    # TODO: verificar strings exactos en el portal real
    _TARJETAS = ["Platinum Credit Card", "Platinum Card"]

    def check_session(self, driver) -> bool:
        try:
            driver.get(_ACCOUNT)
            time.sleep(3)
            # TODO: selector de elemento que solo aparece logueado
            el = self.find(driver,
                "[data-module-name='axp-member-greeting'], "
                ".user-account-module, [data-testid='axp-greeting'], "
                ".account-summary"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[amex] check_session: %s", exc)
            return False

    def do_login(self, driver, config: dict) -> None:
        driver.get(_LOGIN_URL)
        time.sleep(2)

        # ── Usuario ────────────────────────────────────────────────────────────
        # TODO: verificar selector
        user_el = self.wait_for(driver,
            "input[id='eliloUserID'], input[name='login'], "
            "input[type='email'], input[autocomplete='username']",
            timeout=15,
        )
        user_el.clear()
        user_el.send_keys(config["usuario"])
        time.sleep(0.5)

        # TODO: ¿AMEX separa usuario y contraseña en dos pantallas?
        cont = self.find(driver, "button#loginSubmit, input[type='submit']")
        if cont:
            try:
                cont.click()
                time.sleep(2)
            except Exception:
                pass

        # ── Contraseña ─────────────────────────────────────────────────────────
        # TODO: verificar selector
        pass_el = self.wait_for(driver,
            "input[id='eliloPassword'], input[type='password'], "
            "input[autocomplete='current-password']",
            timeout=10,
        )
        pass_el.clear()
        pass_el.send_keys(config["password"])
        time.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        # TODO: verificar selector
        submit = self.wait_for(driver, "button#loginSubmit, button[type='submit']", timeout=10)
        submit.click()

        # Esperar dashboard post-login
        # TODO: verificar selector
        self.wait_for(driver,
            "[data-module-name='axp-member-greeting'], .account-summary",
            timeout=30,
        )
        logger.info("[amex] Login OK")

    def scrape(self, driver, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        for tarjeta_nombre in self._TARJETAS:
            try:
                movs, saldo = self._scrape_tarjeta(driver, tarjeta_nombre)
                movimientos.extend(movs)
                if saldo is not None:
                    prev = saldos.get("amex", {})
                    saldos["amex"] = {"saldo_ars": (prev.get("saldo_ars") or 0.0) + saldo}
            except Exception as exc:
                logger.error("[amex] Error scrapeando '%s': %s", tarjeta_nombre, exc)

        return ScraperResult(fuente="amex", movimientos=movimientos, saldos=saldos)

    def _scrape_tarjeta(
        self, driver, tarjeta_nombre: str
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        TODO: navegar a la tarjeta y extraer movimientos + saldo.

        Pasos típicos en AMEX:
          1. Selector de tarjeta (dropdown o pestañas con nombres/números)
          2. Navegar a sección "Actividad reciente"
          3. Saldo (total a pagar del período actual)
          4. Filas ARS y USD (AMEX suele separar los cargos por moneda)
        """
        logger.warning("[amex] _scrape_tarjeta('%s') — TODO: implementar", tarjeta_nombre)
        return [], None

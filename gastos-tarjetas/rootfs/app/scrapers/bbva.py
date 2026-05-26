"""
Scraper BBVA Argentina — Selenium.

Un login → tres productos: bbva_mc, bbva_visa, bbva_cuenta.
Sin OTP: usuario + contraseña + tercer_dato estático.

CALIBRACIÓN REQUERIDA:
  Abrir https://www.bbva.com.ar en un browser, hacer login manual, usar
  DevTools → Inspector para identificar los selectores reales y reemplazar
  los marcados con TODO.

  Para depurar: temporalmente cambiar `--headless=new` a `--headless=false`
  en base.py _create_driver() y correr el scraper manual desde la UI.
"""

import logging
import time

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL   = "https://www.bbva.com.ar/personas/home.html"
_DASHBOARD   = "https://www.bbva.com.ar/personas/homebanking.html"


class BbvaScraper(BaseScraper):
    fuente       = "bbva"
    nombre       = "BBVA Argentina"
    login_origin = "https://www.bbva.com.ar"

    # ── check_session ─────────────────────────────────────────────────────────

    def check_session(self, driver) -> bool:
        try:
            driver.get(_DASHBOARD)
            time.sleep(3)
            # TODO: reemplazar con selector real del elemento post-login
            el = self.find(driver,
                "[data-testid='user-greeting'], .bbva-user-name, "
                "#userGreeting, .home-dashboard"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[bbva] check_session: %s", exc)
            return False

    # ── do_login ──────────────────────────────────────────────────────────────

    def do_login(self, driver, config: dict) -> None:
        usuario     = config["usuario"]
        password    = config["password"]
        tercer_dato = config.get("tercer_dato", "")

        driver.get(_LOGIN_URL)
        time.sleep(2)

        # ── Usuario ────────────────────────────────────────────────────────────
        # TODO: verificar selector con DevTools
        user_el = self.wait_for(driver,
            "input[name='user'], input[placeholder*='usuario' i], "
            "input[id*='user' i], input[autocomplete='username']",
            timeout=15,
        )
        user_el.clear()
        user_el.send_keys(usuario)
        time.sleep(0.5)

        # TODO: ¿hay botón "Continuar" antes de la contraseña?
        btn_cont = self.find(driver,
            "button[type='submit']:not([disabled]), "
            "button:has-text('Continuar')"  # nota: :has-text es Playwright; en Selenium buscar por texto
        )
        # Alternativa para buscar por texto en Selenium:
        # btn_cont = self.find(driver, "button[type='submit']")
        if btn_cont:
            try:
                btn_cont.click()
                time.sleep(2)
            except Exception:
                pass

        # ── Contraseña ─────────────────────────────────────────────────────────
        # TODO: verificar selector
        pass_el = self.wait_for(driver,
            "input[type='password'], input[name='password'], "
            "input[autocomplete='current-password']",
            timeout=10,
        )
        pass_el.clear()
        pass_el.send_keys(password)
        time.sleep(0.5)

        # ── Tercer dato (si existe) ────────────────────────────────────────────
        # TODO: verificar si BBVA pide un tercer campo y su selector
        if tercer_dato:
            third_el = self.find(driver,
                "input[name='thirdFactor'], input[placeholder*='cuil' i], "
                "input[placeholder*='documento' i]"
            )
            if third_el:
                third_el.clear()
                third_el.send_keys(tercer_dato)
                time.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        # TODO: verificar selector del botón final
        submit = self.wait_for(driver,
            "button[type='submit']",
            timeout=10,
        )
        submit.click()

        # Esperar dashboard post-login
        # TODO: verificar selector del elemento que aparece solo logueado
        self.wait_for(driver,
            "[data-testid='user-greeting'], .bbva-home, "
            ".home-dashboard, #dashboardContainer",
            timeout=30,
        )
        logger.info("[bbva] Login OK")

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        for fuente_prod, nombre_prod in [
            ("bbva_mc",     "Mastercard"),
            ("bbva_visa",   "Visa"),
        ]:
            try:
                movs, saldo = self._scrape_tarjeta(driver, fuente_prod, nombre_prod)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos[fuente_prod] = {"saldo_ars": saldo}
            except Exception as exc:
                logger.error("[bbva] Error scrapeando %s: %s", fuente_prod, exc)

        try:
            movs, saldo = self._scrape_cuenta(driver)
            movimientos.extend(movs)
            if saldo is not None:
                saldos["bbva_cuenta"] = {"saldo_ars": saldo}
        except Exception as exc:
            logger.error("[bbva] Error scrapeando cuenta: %s", exc)

        return ScraperResult(fuente="bbva", movimientos=movimientos, saldos=saldos)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _scrape_tarjeta(
        self, driver, fuente: str, nombre: str
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        TODO: implementar navegación a la sección de tarjetas de BBVA
        y extracción de filas de movimientos.

        Pasos típicos:
          1. driver.get(URL_TARJETAS) o clic en sección "Tarjetas"
          2. Seleccionar MC o Visa por su nombre/número
          3. Extraer saldo total
          4. Extraer filas: fecha | descripción | importe
        """
        logger.warning("[bbva] _scrape_tarjeta(%s) — TODO: implementar", fuente)

        # ── STUB — reemplazar con código real ──────────────────────────────────
        # time.sleep(2)
        # driver.get("https://www.bbva.com.ar/personas/homebanking/tarjetas.html")
        # # 1. Seleccionar tarjeta
        # tarjeta_el = self.find(driver, f"[data-card-name*='{nombre}']")
        # if tarjeta_el:
        #     tarjeta_el.click(); time.sleep(2)
        # # 2. Saldo
        # saldo_el = self.find(driver, ".saldo-total, [data-field='balance']")
        # saldo = self.parse_amount(saldo_el.text) if saldo_el else None
        # # 3. Filas
        # movimientos = []
        # for row in self.find_all(driver, "table.movimientos tr, .lista-ops .row"):
        #     cols = row.find_elements("css selector", "td, .col")
        #     if len(cols) < 3: continue
        #     fecha = self.parse_date_ar(cols[0].text.strip())
        #     if not fecha: continue
        #     monto = self.parse_amount(cols[2].text.strip())
        #     movimientos.append(MovimientoRaw(
        #         fuente=fuente, fecha=fecha,
        #         descripcion=cols[1].text.strip(), monto=monto,
        #     ))
        # return movimientos, saldo
        # ── FIN STUB ───────────────────────────────────────────────────────────

        return [], None

    def _scrape_cuenta(
        self, driver
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        TODO: implementar extracción de movimientos de la Cuenta $ BBVA.
        Similar a _scrape_tarjeta pero navegando a la sección "Cuentas".
        """
        logger.warning("[bbva] _scrape_cuenta — TODO: implementar")
        return [], None

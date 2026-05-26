"""
Scraper BBVA Argentina.

Un login → tres productos: Mastercard (bbva_mc), Visa (bbva_visa), Cuenta $ (bbva_cuenta).
Autenticación: usuario + contraseña + tercer_dato (dato estático fijo, sin OTP).

Portal: https://www.bbva.com.ar/personas/home.html

CALIBRACIÓN REQUERIDA:
  Antes de usar este scraper hay que verificar los selectores CSS/XPath contra
  el portal real. Cada selector marcado con TODO debe confirmarse abriendo el
  portal en un browser y usando DevTools.

  Forma rápida de depurar: en scraper_scheduler.py poner headless=False
  (o pasar "debug": true en scrapers.yaml) y observar el browser.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

# ── URLs ──────────────────────────────────────────────────────────────────────
_BASE    = "https://www.bbva.com.ar"
_LOGIN   = f"{_BASE}/personas/home.html"
_SUMMARY = f"{_BASE}/personas/homebanking.html"   # URL post-login (a verificar)

# ── Horizonte de scraping ─────────────────────────────────────────────────────
_DIAS_ATRAS = 45   # cuántos días de movimientos buscar


class BbvaScraper(BaseScraper):
    fuente = "bbva"
    nombre = "BBVA Argentina"

    # ── check_session ──────────────────────────────────────────────────────────

    async def check_session(self, page) -> bool:
        """Navega al home y verifica que no redirija al login."""
        try:
            await page.goto(_SUMMARY, timeout=20_000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # TODO: ajustar selector — buscar un elemento que solo aparece logueado
            # Ejemplo: un elemento de bienvenida o el menú de usuario
            is_logged = await page.query_selector(
                # selector de un elemento que solo existe con sesión activa
                # ej. "[data-testid='user-menu']" o ".home-banking-nav"
                "[data-testid='user-greeting'], .bbva-user-name, #userGreeting"
            )
            return is_logged is not None
        except Exception as exc:
            logger.debug("[bbva] check_session error: %s", exc)
            return False

    # ── do_login ───────────────────────────────────────────────────────────────

    async def do_login(self, page, config: dict) -> None:
        """
        Login en BBVA Argentina con usuario + contraseña + tercer dato.

        El portal puede variar; los selectores a continuación son orientativos.
        Ajustar con DevTools si el login falla.
        """
        usuario     = config["usuario"]
        password    = config["password"]
        tercer_dato = config.get("tercer_dato", "")

        await page.goto(_LOGIN, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # ── Paso 1: usuario ────────────────────────────────────────────────────
        # TODO: verificar selector del campo de usuario
        user_input = await page.wait_for_selector(
            "input[name='user'], input[placeholder*='usuario' i], "
            "input[id*='user' i], input[autocomplete='username']",
            timeout=15_000,
        )
        await user_input.fill(usuario)
        await asyncio.sleep(0.5)

        # TODO: verificar si hay botón "Continuar" antes del campo de contraseña
        continuar = await page.query_selector(
            "button[type='submit'], button:has-text('Continuar'), "
            "button:has-text('Siguiente')"
        )
        if continuar:
            await continuar.click()
            await asyncio.sleep(2)

        # ── Paso 2: contraseña ─────────────────────────────────────────────────
        # TODO: verificar selector del campo de contraseña
        pass_input = await page.wait_for_selector(
            "input[type='password'], input[name='password'], "
            "input[autocomplete='current-password']",
            timeout=10_000,
        )
        await pass_input.fill(password)
        await asyncio.sleep(0.5)

        # ── Paso 3: tercer dato ────────────────────────────────────────────────
        # TODO: si BBVA pide un tercer campo (ej. CUIL, PIN adicional, respuesta
        # de seguridad), buscar su selector y rellenarlo aquí.
        # Si tercer_dato está configurado, buscamos el campo:
        if tercer_dato:
            third_input = await page.query_selector(
                "input[name='thirdFactor'], input[placeholder*='cuil' i], "
                "input[placeholder*='documento' i], input[data-field='extra']"
            )
            if third_input:
                await third_input.fill(tercer_dato)
                await asyncio.sleep(0.5)

        # ── Enviar formulario ──────────────────────────────────────────────────
        # TODO: verificar selector del botón final de login
        submit = await page.wait_for_selector(
            "button[type='submit']:has-text('Ingresar'), "
            "button:has-text('Ingresar'), button:has-text('Entrar')",
            timeout=10_000,
        )
        await submit.click()

        # Esperar que cargue el home post-login
        # TODO: ajustar el selector del elemento que confirma login exitoso
        await page.wait_for_selector(
            "[data-testid='user-greeting'], .bbva-home, "
            ".home-dashboard, #dashboardContainer",
            timeout=30_000,
        )
        logger.info("[bbva] Login OK")

    # ── scrape ─────────────────────────────────────────────────────────────────

    async def scrape(self, page, config: dict) -> ScraperResult:
        """
        Una vez logueado, raspa los tres productos BBVA:
          - Mastercard  → bbva_mc
          - Visa        → bbva_visa
          - Cuenta $    → bbva_cuenta
        """
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        try:
            mc_movs, mc_saldo = await self._scrape_tarjeta(page, "bbva_mc")
            movimientos.extend(mc_movs)
            if mc_saldo is not None:
                saldos["bbva_mc"] = {"saldo_ars": mc_saldo}
        except Exception as exc:
            logger.error("[bbva] Error scrapeando MC: %s", exc)

        try:
            visa_movs, visa_saldo = await self._scrape_tarjeta(page, "bbva_visa")
            movimientos.extend(visa_movs)
            if visa_saldo is not None:
                saldos["bbva_visa"] = {"saldo_ars": visa_saldo}
        except Exception as exc:
            logger.error("[bbva] Error scrapeando Visa: %s", exc)

        try:
            cuenta_movs, cuenta_saldo = await self._scrape_cuenta(page)
            movimientos.extend(cuenta_movs)
            if cuenta_saldo is not None:
                saldos["bbva_cuenta"] = {"saldo_ars": cuenta_saldo}
        except Exception as exc:
            logger.error("[bbva] Error scrapeando Cuenta: %s", exc)

        return ScraperResult(
            fuente="bbva",
            movimientos=movimientos,
            saldos=saldos,
        )

    # ── helpers internos ───────────────────────────────────────────────────────

    async def _scrape_tarjeta(
        self, page, fuente: str
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Raspa los movimientos de una tarjeta (MC o Visa).
        Devuelve (movimientos, saldo_total).

        TODO: implementar navegación real al producto correcto y
              extracción de filas de la tabla de movimientos.

        Estructura típica BBVA:
          - Sección "Tarjetas" en el sidebar/dashboard
          - Clic en la tarjeta (MC o Visa)
          - Sección "Últimas operaciones" con filas: Fecha | Descripción | Importe
          - Puede haber paginación o scroll infinito
        """
        logger.warning("[bbva] _scrape_tarjeta(%s) — TODO: implementar", fuente)

        # ── STUB ───────────────────────────────────────────────────────────────
        # Reemplazar con código real de Playwright cuando se calibre:
        #
        # 1. Navegar a la sección de tarjetas
        # await page.click("a[href*='tarjetas'], button:has-text('Tarjetas')")
        # await asyncio.sleep(1)
        #
        # 2. Seleccionar la tarjeta correcta (MC o Visa)
        # tarjeta_label = "Mastercard" if fuente == "bbva_mc" else "Visa"
        # await page.click(f"text={tarjeta_label}")
        # await asyncio.sleep(2)
        #
        # 3. Extraer saldo
        # saldo_text = await page.inner_text(".saldo-total, [data-field='balance']")
        # saldo = self.parse_amount(saldo_text)
        #
        # 4. Extraer filas de movimientos
        # rows = await page.query_selector_all("table.movimientos tr, .lista-ops .op-row")
        # for row in rows:
        #     cols = await row.query_selector_all("td, .col")
        #     if len(cols) < 3:
        #         continue
        #     fecha_text = await cols[0].inner_text()
        #     desc_text  = await cols[1].inner_text()
        #     monto_text = await cols[2].inner_text()
        #     fecha = self.parse_date_ar(fecha_text.strip())
        #     if not fecha:
        #         continue
        #     monto = self.parse_amount(monto_text.strip())
        #     movimientos.append(MovimientoRaw(
        #         fuente=fuente, fecha=fecha,
        #         descripcion=desc_text.strip(), monto=monto,
        #     ))
        # ── FIN STUB ───────────────────────────────────────────────────────────

        return [], None

    async def _scrape_cuenta(
        self, page
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Raspa los movimientos de la Cuenta $ BBVA.
        Devuelve (movimientos, saldo_disponible).

        TODO: misma lógica que _scrape_tarjeta pero navegando a "Cuentas".
        Diferencia: monto positivo = egreso (débito), negativo = ingreso (crédito).
        El saldo es el saldo disponible de la cuenta, no el total a pagar.
        """
        logger.warning("[bbva] _scrape_cuenta — TODO: implementar")
        return [], None

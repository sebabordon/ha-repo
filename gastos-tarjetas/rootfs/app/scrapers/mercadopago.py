"""
Scraper MercadoPago Argentina.

Un login → cuenta MP (saldo + movimientos).
Autenticación: email/teléfono + contraseña.
Nota: MP puede pedir 2FA por SMS/mail. Si eso ocurre, el scraper marca
      session_expired y el usuario deberá regenerar la sesión manualmente
      (similar al flujo TOTP de Galicia, a implementar si es necesario).

Portal: https://www.mercadopago.com.ar/

CALIBRACIÓN REQUERIDA:
  Verificar selectores con DevTools antes de activar.
  MP usa React con data-testid attrs — esos son más estables que clases CSS.
"""

import asyncio
import logging

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN    = "https://www.mercadopago.com.ar/hub/login"
_ACTIVITY = "https://www.mercadopago.com.ar/activities"  # a verificar


class MercadoPagoScraper(BaseScraper):
    fuente = "mercadopago"
    nombre = "MercadoPago"

    async def check_session(self, page) -> bool:
        try:
            await page.goto(_ACTIVITY, timeout=20_000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # TODO: verificar selector de elemento post-login
            el = await page.query_selector(
                "[data-testid='navbar-user-avatar'], .nav-user-avatar, "
                "#nav-header-user, [data-testid='activity-list']"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[mp] check_session error: %s", exc)
            return False

    async def do_login(self, page, config: dict) -> None:
        usuario  = config["usuario"]
        password = config["password"]

        await page.goto(_LOGIN, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # ── Email / teléfono ───────────────────────────────────────────────────
        # TODO: verificar selector — MP suele usar data-testid
        user_input = await page.wait_for_selector(
            "input[data-testid='login-identifier-input'], "
            "input[name='user_id'], input[type='email'], "
            "input[placeholder*='email' i], input[placeholder*='celular' i]",
            timeout=15_000,
        )
        await user_input.fill(usuario)
        await asyncio.sleep(0.5)

        # ── Continuar ──────────────────────────────────────────────────────────
        # TODO: MP puede tener un botón de "Continuar" antes de la contraseña
        continuar = await page.query_selector(
            "button[data-testid='action-next'], "
            "button:has-text('Continuar'), button[type='submit']"
        )
        if continuar:
            await continuar.click()
            await asyncio.sleep(2)

        # ── Contraseña ─────────────────────────────────────────────────────────
        # TODO: verificar selector
        pass_input = await page.wait_for_selector(
            "input[data-testid='password-input'], input[type='password'], "
            "input[name='password'], input[autocomplete='current-password']",
            timeout=10_000,
        )
        await pass_input.fill(password)
        await asyncio.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        submit = await page.wait_for_selector(
            "button[data-testid='action-confirm'], "
            "button:has-text('Ingresar'), button[type='submit']",
            timeout=10_000,
        )
        await submit.click()

        # Esperar resultado: home o pantalla de 2FA
        # TODO: ajustar selectores
        try:
            await page.wait_for_selector(
                "[data-testid='activity-list'], .nav-user-avatar, "
                "[data-testid='2fa-input'], input[placeholder*='código' i]",
                timeout=30_000,
            )
        except Exception:
            raise RuntimeError("MercadoPago: timeout esperando dashboard o 2FA")

        # Detectar 2FA
        two_fa = await page.query_selector(
            "[data-testid='2fa-input'], input[placeholder*='código' i]"
        )
        if two_fa:
            raise RuntimeError(
                "MercadoPago requiere 2FA. Sesión no iniciada automáticamente. "
                "Verificá que la cuenta no tenga 2FA obligatorio o deshabilitalo temporalmente."
            )

        logger.info("[mp] Login OK")

    async def scrape(self, page, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        try:
            movs, saldo = await self._scrape_cuenta(page)
            movimientos.extend(movs)
            if saldo is not None:
                saldos["mercadopago"] = {"saldo_ars": saldo}
        except Exception as exc:
            logger.error("[mp] Error scrapeando cuenta: %s", exc)

        return ScraperResult(
            fuente="mercadopago",
            movimientos=movimientos,
            saldos=saldos,
        )

    async def _scrape_cuenta(
        self, page
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Extrae movimientos y saldo disponible de la cuenta MercadoPago.

        TODO: implementar navegación y extracción.

        Estructura típica MP:
          - Saldo disponible: widget en el home o en /activities
          - Lista de movimientos: /activities, filas con fecha, descripción, monto
          - Ingresos: monto negativo en nuestra convención (monto < 0)
          - Egresos: monto positivo (monto > 0)
          - Moneda: siempre ARS para la cuenta pesos
        """
        logger.warning("[mp] _scrape_cuenta — TODO: implementar")

        # ── STUB ───────────────────────────────────────────────────────────────
        # Reemplazar con código real:
        #
        # await page.goto(_ACTIVITY, wait_until="domcontentloaded")
        # await asyncio.sleep(2)
        #
        # # Saldo disponible
        # saldo_el = await page.query_selector(
        #     "[data-testid='available-money'], .available-amount"
        # )
        # saldo = self.parse_amount(await saldo_el.inner_text()) if saldo_el else None
        #
        # # Movimientos
        # rows = await page.query_selector_all(
        #     "[data-testid='activity-row'], .activity-item"
        # )
        # for row in rows:
        #     fecha_el = await row.query_selector("[data-testid='date'], .activity-date")
        #     desc_el  = await row.query_selector("[data-testid='description'], .activity-title")
        #     monto_el = await row.query_selector("[data-testid='amount'], .activity-amount")
        #     if not (fecha_el and desc_el and monto_el):
        #         continue
        #     fecha = self.parse_date_ar(await fecha_el.inner_text())
        #     if not fecha:
        #         continue
        #     monto_raw = self.parse_amount(await monto_el.inner_text())
        #     # En MP: ingreso (depósito) = positivo en pantalla → negativo en nuestra conv.
        #     # Egreso (pago/retiro) = negativo en pantalla → positivo en nuestra conv.
        #     # TODO: verificar el signo según cómo MP muestra los importes
        #     movimientos.append(MovimientoRaw(
        #         fuente="mercadopago",
        #         fecha=fecha,
        #         descripcion=(await desc_el.inner_text()).strip(),
        #         monto=monto_raw,   # ajustar signo si es necesario
        #         moneda="ARS",
        #     ))
        # ── FIN STUB ───────────────────────────────────────────────────────────

        return [], None

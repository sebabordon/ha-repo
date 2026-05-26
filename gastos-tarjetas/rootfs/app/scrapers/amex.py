"""
Scraper AMEX Argentina.

Un login → dos tarjetas: Platinum Credit Card y Platinum Card.
Autenticación: usuario (email) + contraseña (sin OTP).
Ambas tarjetas van a fuente='amex' en gastos (decisión arquitectural: Opción A).
El campo `tarjeta` en movimientos_raw distingue "Platinum Credit" vs "Platinum Card".

Portal: https://online.americanexpress.com/myca/logon/emea/action?request_type=LogLogonHandler&DestPage=...
  (o la versión argentina: https://www.americanexpress.com/es-ar/account/login)

CALIBRACIÓN REQUERIDA:
  Verificar selectores con DevTools antes de activar.
"""

import asyncio
import logging

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

# ── URLs ──────────────────────────────────────────────────────────────────────
_LOGIN   = "https://www.americanexpress.com/es-ar/account/login"
_ACCOUNT = "https://www.americanexpress.com/es-ar/account/activity"  # a verificar


class AmexScraper(BaseScraper):
    fuente = "amex"
    nombre = "AMEX Argentina"

    # Nombres de tarjeta tal como aparecen en el portal AMEX
    # TODO: verificar los strings exactos
    _TARJETAS = [
        "Platinum Credit Card",
        "Platinum Card",
    ]

    async def check_session(self, page) -> bool:
        try:
            await page.goto(_ACCOUNT, timeout=20_000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # TODO: verificar selector de elemento post-login
            el = await page.query_selector(
                "[data-module-name='axp-member-greeting'], "
                ".user-account-module, [data-testid='axp-greeting']"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[amex] check_session error: %s", exc)
            return False

    async def do_login(self, page, config: dict) -> None:
        usuario  = config["usuario"]
        password = config["password"]

        await page.goto(_LOGIN, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # ── Campo de usuario ───────────────────────────────────────────────────
        # TODO: verificar selector
        user_input = await page.wait_for_selector(
            "input[id='eliloUserID'], input[name='login'], "
            "input[type='email'], input[autocomplete='username']",
            timeout=15_000,
        )
        await user_input.fill(usuario)
        await asyncio.sleep(0.5)

        # ── Botón Continuar (si AMEX separa usuario y contraseña en dos pantallas) ──
        continuar = await page.query_selector(
            "button#loginSubmit, button:has-text('Continuar'), "
            "button:has-text('Next'), input[type='submit']"
        )
        if continuar:
            await continuar.click()
            await asyncio.sleep(2)

        # ── Campo de contraseña ────────────────────────────────────────────────
        # TODO: verificar selector
        pass_input = await page.wait_for_selector(
            "input[id='eliloPassword'], input[type='password'], "
            "input[name='password'], input[autocomplete='current-password']",
            timeout=10_000,
        )
        await pass_input.fill(password)
        await asyncio.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        # TODO: verificar selector
        submit = await page.wait_for_selector(
            "button#loginSubmit, button[type='submit']:has-text('Ingresar'), "
            "button:has-text('Log In'), button:has-text('Iniciar sesión')",
            timeout=10_000,
        )
        await submit.click()

        # Esperar home post-login
        # TODO: verificar selector de elemento post-login
        await page.wait_for_selector(
            "[data-module-name='axp-member-greeting'], .user-account-module, "
            "[data-testid='axp-greeting'], .account-summary",
            timeout=30_000,
        )
        logger.info("[amex] Login OK")

    async def scrape(self, page, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        for tarjeta_nombre in self._TARJETAS:
            try:
                movs, saldo = await self._scrape_tarjeta(page, tarjeta_nombre)
                movimientos.extend(movs)
                if saldo is not None:
                    # Ambas tarjetas contribuyen al saldo bajo 'amex'
                    prev = saldos.get("amex", {})
                    saldos["amex"] = {
                        "saldo_ars": (prev.get("saldo_ars", 0.0) or 0.0) + saldo
                    }
            except Exception as exc:
                logger.error("[amex] Error scrapeando '%s': %s", tarjeta_nombre, exc)

        return ScraperResult(
            fuente="amex",
            movimientos=movimientos,
            saldos=saldos,
        )

    async def _scrape_tarjeta(
        self, page, tarjeta_nombre: str
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Navega a la tarjeta `tarjeta_nombre` y extrae movimientos y saldo.

        TODO: implementar la navegación real. AMEX suele mostrar un selector
        de tarjetas (dropdown o lista) cuando hay más de una.

        Estructura típica AMEX Argentina:
          - Selector de tarjeta: dropdown o pestaña con el nombre/número
          - Sección "Cargos del período" con filas:
              Fecha | Descripción | Importe (ARS o USD)
          - Puede haber dos secciones: "Cargos en Pesos" y "Cargos en Dólares"
        """
        logger.warning("[amex] _scrape_tarjeta('%s') — TODO: implementar", tarjeta_nombre)

        # ── STUB ───────────────────────────────────────────────────────────────
        # Reemplazar con código real:
        #
        # 1. Seleccionar la tarjeta
        # card_selector = await page.query_selector(
        #     f"[data-card-name*='{tarjeta_nombre}'], "
        #     f"option:has-text('{tarjeta_nombre}')"
        # )
        # if card_selector:
        #     await card_selector.click()
        #     await asyncio.sleep(2)
        #
        # 2. Navegar a actividad reciente
        # await page.goto(_ACCOUNT, wait_until="domcontentloaded")
        # await asyncio.sleep(2)
        #
        # 3. Extraer saldo (total a pagar)
        # saldo_el = await page.query_selector(".balance-amount, [data-field='balance']")
        # saldo = self.parse_amount(await saldo_el.inner_text()) if saldo_el else None
        #
        # 4. Extraer movimientos ARS
        # rows = await page.query_selector_all(".transaction-row, tr.charge-row")
        # for row in rows:
        #     fecha_el  = await row.query_selector(".transaction-date, td:nth-child(1)")
        #     desc_el   = await row.query_selector(".transaction-description, td:nth-child(2)")
        #     monto_el  = await row.query_selector(".transaction-amount, td:nth-child(3)")
        #     if not (fecha_el and desc_el and monto_el):
        #         continue
        #     fecha = self.parse_date_ar(await fecha_el.inner_text())
        #     if not fecha:
        #         continue
        #     monto = self.parse_amount(await monto_el.inner_text())
        #     movimientos.append(MovimientoRaw(
        #         fuente="amex", fecha=fecha,
        #         descripcion=(await desc_el.inner_text()).strip(),
        #         monto=monto, moneda="ARS",
        #         tarjeta=tarjeta_nombre,
        #     ))
        # ── FIN STUB ───────────────────────────────────────────────────────────

        return [], None

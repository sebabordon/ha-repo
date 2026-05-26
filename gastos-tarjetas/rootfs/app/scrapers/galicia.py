"""
Scraper Banco Galicia Argentina.

Un login → Mastercard + Cuenta $ (por ahora solo MC).
Autenticación: usuario + contraseña + TOTP inicial (mail o app).
  - Primera vez: flujo interactivo con TOTP vía la UI del add-on.
  - Runs posteriores: sesión persistida en /data/sessions/galicia.json.

Portal: https://www.bancogalicia.com.ar/banca-en-linea/

CALIBRACIÓN REQUERIDA:
  Verificar selectores con DevTools antes de activar.
"""

import asyncio
import logging
import uuid
from typing import Optional

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_BASE     = "https://www.bancogalicia.com.ar"
_LOGIN    = f"{_BASE}/banca-en-linea/"
_DASHBOARD = f"{_BASE}/banca-en-linea/home"   # a verificar

# ── Estado global para el flujo interactivo de TOTP ───────────────────────────
# {request_id: asyncio.Queue}  — la queue recibe el código TOTP del endpoint HTTP
_pending_totp: dict[str, asyncio.Queue] = {}


class GaliciaScraper(BaseScraper):
    fuente = "galicia"
    nombre = "Banco Galicia"

    async def check_session(self, page) -> bool:
        try:
            await page.goto(_DASHBOARD, timeout=20_000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # TODO: verificar selector de elemento post-login (ej. nombre de usuario)
            el = await page.query_selector(
                ".user-name, [data-testid='user-name'], "
                ".home-dashboard, #dashboardContent"
            )
            return el is not None
        except Exception as exc:
            logger.debug("[galicia] check_session error: %s", exc)
            return False

    async def do_login(self, page, config: dict) -> None:
        """
        Login estándar con sesión guardada.
        Si se necesita TOTP se lanza SessionExpiredError (el scheduler lo captura
        y pone estado='session_expired' para que la UI notifique al usuario).
        """
        usuario  = config["usuario"]
        password = config["password"]

        await page.goto(_LOGIN, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # ── Usuario ────────────────────────────────────────────────────────────
        # TODO: verificar selector
        user_input = await page.wait_for_selector(
            "input[name='username'], input[id*='user' i], "
            "input[placeholder*='usuario' i], input[autocomplete='username']",
            timeout=15_000,
        )
        await user_input.fill(usuario)
        await asyncio.sleep(0.5)

        # ── Contraseña ─────────────────────────────────────────────────────────
        # TODO: verificar selector (puede estar en una segunda pantalla)
        pass_input = await page.wait_for_selector(
            "input[type='password'], input[name='password'], "
            "input[autocomplete='current-password']",
            timeout=10_000,
        )
        await pass_input.fill(password)
        await asyncio.sleep(0.5)

        # ── Submit ─────────────────────────────────────────────────────────────
        # TODO: verificar selector
        submit = await page.wait_for_selector(
            "button[type='submit'], button:has-text('Ingresar'), "
            "button:has-text('Iniciar sesión')",
            timeout=10_000,
        )
        await submit.click()

        # Esperar resultado: home post-login OR pantalla de TOTP
        # TODO: ajustar selectores de ambos estados
        try:
            await page.wait_for_selector(
                ".home-dashboard, #dashboardContent, "
                "[data-testid='totp-input'], input[placeholder*='código' i], "
                ".otp-input, #otpCode",
                timeout=30_000,
            )
        except Exception:
            raise RuntimeError(
                "Galicia: timeout esperando dashboard o pantalla de TOTP"
            )

        # Detectar si llegamos al TOTP
        # TODO: ajustar selector de la pantalla de TOTP
        totp_screen = await page.query_selector(
            "[data-testid='totp-input'], input[placeholder*='código' i], "
            ".otp-input, #otpCode, input[maxlength='6']"
        )
        if totp_screen:
            # El scraper automático no puede completar TOTP sin interacción humana.
            # Marcamos session_expired para que la UI notifique al usuario.
            raise _SessionNeedsTotp(
                "Galicia requiere TOTP. Usá 'Configurar sesión Galicia' en la UI."
            )

        logger.info("[galicia] Login OK (sin TOTP)")

    async def scrape(self, page, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        try:
            movs, saldo = await self._scrape_mastercard(page)
            movimientos.extend(movs)
            if saldo is not None:
                saldos["galicia_mc"] = {"saldo_ars": saldo}
        except Exception as exc:
            logger.error("[galicia] Error scrapeando MC: %s", exc)

        return ScraperResult(
            fuente="galicia",
            movimientos=movimientos,
            saldos=saldos,
        )

    async def _scrape_mastercard(
        self, page
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Extrae movimientos de Galicia Mastercard.

        TODO: implementar navegación al módulo de tarjeta y extracción de filas.

        Estructura típica Galicia:
          - Sección "Tarjetas" en el menú lateral
          - Filas de "Últimos movimientos": Fecha | Descripción | Importe
          - Importes en ARS o USD (verificar cómo los distingue Galicia)
        """
        logger.warning("[galicia] _scrape_mastercard — TODO: implementar")
        return [], None

    # ── Flujo interactivo de TOTP ──────────────────────────────────────────────

    async def start_session_setup(self, config: dict) -> str:
        """
        Inicia el flujo interactivo de configuración de sesión con TOTP.
        Devuelve un request_id que el cliente usará para enviar el código.
        El proceso corre como asyncio.Task en background.
        """
        request_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _pending_totp[request_id] = queue

        asyncio.create_task(
            self._run_totp_setup(config, request_id, queue),
            name=f"galicia_totp_{request_id[:8]}",
        )
        return request_id

    async def submit_totp_code(self, request_id: str, code: str) -> bool:
        """Envía el código TOTP al task que lo está esperando."""
        q = _pending_totp.get(request_id)
        if not q:
            return False
        await q.put(code)
        return True

    def get_pending_totp_ids(self) -> list[str]:
        """Lista de request_ids con TOTP pendiente."""
        return list(_pending_totp.keys())

    async def _run_totp_setup(
        self, config: dict, request_id: str, queue: asyncio.Queue
    ) -> None:
        """
        Task en background: hace login, espera el TOTP del usuario y completa la sesión.
        """
        from playwright.async_api import async_playwright
        import os

        chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")

        try:
            async with async_playwright() as p:
                launch_opts: dict = {"headless": True, "args": ["--no-sandbox"]}
                if chromium_path:
                    launch_opts["executable_path"] = chromium_path

                browser = await p.chromium.launch(**launch_opts)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()

                try:
                    usuario  = config["usuario"]
                    password = config["password"]

                    await page.goto(_LOGIN, timeout=30_000, wait_until="domcontentloaded")
                    await asyncio.sleep(2)

                    # ── Usuario ────────────────────────────────────────────────
                    # TODO: mismo selector que do_login
                    user_input = await page.wait_for_selector(
                        "input[name='username'], input[id*='user' i], "
                        "input[placeholder*='usuario' i]",
                        timeout=15_000,
                    )
                    await user_input.fill(usuario)
                    await asyncio.sleep(0.5)

                    # ── Contraseña ─────────────────────────────────────────────
                    # TODO: mismo selector que do_login
                    pass_input = await page.wait_for_selector(
                        "input[type='password']",
                        timeout=10_000,
                    )
                    await pass_input.fill(password)

                    submit = await page.wait_for_selector(
                        "button[type='submit'], button:has-text('Ingresar')",
                        timeout=10_000,
                    )
                    await submit.click()

                    # ── Esperar pantalla de TOTP ───────────────────────────────
                    # TODO: ajustar selector
                    totp_input = await page.wait_for_selector(
                        "[data-testid='totp-input'], input[placeholder*='código' i], "
                        ".otp-input, #otpCode, input[maxlength='6']",
                        timeout=30_000,
                    )
                    logger.info("[galicia_setup] Pantalla de TOTP detectada, esperando código…")

                    # Esperar el código del usuario (timeout 5 min)
                    try:
                        code = await asyncio.wait_for(queue.get(), timeout=300)
                    except asyncio.TimeoutError:
                        logger.warning("[galicia_setup] Timeout esperando TOTP")
                        return

                    # ── Ingresar el código TOTP ────────────────────────────────
                    await totp_input.fill(code)
                    await asyncio.sleep(0.5)

                    # TODO: botón de confirmar TOTP
                    confirm = await page.query_selector(
                        "button[type='submit'], button:has-text('Confirmar'), "
                        "button:has-text('Verificar'), button:has-text('Continuar')"
                    )
                    if confirm:
                        await confirm.click()

                    # TODO: marcar "recordar este dispositivo" si existe el checkbox
                    remember = await page.query_selector(
                        "input[type='checkbox'][name*='remember' i], "
                        "input[type='checkbox'][id*='remember' i]"
                    )
                    if remember:
                        await remember.check()
                        await asyncio.sleep(0.5)

                    # Esperar el dashboard post-TOTP
                    # TODO: ajustar selector
                    await page.wait_for_selector(
                        ".home-dashboard, #dashboardContent",
                        timeout=30_000,
                    )

                    # Guardar sesión
                    await context.storage_state(path=self.session_path)
                    logger.info("[galicia_setup] Sesión guardada OK")

                    # Actualizar estado
                    from scrapers_db import upsert_scraper_status
                    from datetime import datetime
                    upsert_scraper_status(
                        "galicia",
                        estado="ok",
                        ultimo_ok=datetime.utcnow().isoformat(),
                        error_msg=None,
                    )

                except Exception as exc:
                    logger.exception("[galicia_setup] Error: %s", exc)
                    from scrapers_db import upsert_scraper_status
                    upsert_scraper_status("galicia", estado="error", error_msg=str(exc))
                finally:
                    await context.close()
                    await browser.close()

        except Exception as exc:
            logger.exception("[galicia_setup] Error al lanzar Playwright: %s", exc)
        finally:
            _pending_totp.pop(request_id, None)


class _SessionNeedsTotp(Exception):
    """Indica que se requiere TOTP interactivo (no es un error de credenciales)."""

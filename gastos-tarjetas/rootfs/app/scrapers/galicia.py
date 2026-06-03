"""
Scraper Banco Galicia — Selenium + BFF API (tarjetas Next.js SPA).

Login:
  URL: https://onlinebanking.bancogalicia.com.ar/login
  Formulario (POST a /Users/LogIn):
    - DocumentNumber → config["usuario"]     (DNI, solo dígitos)
    - UserName       → config["tercer_dato"] (alias homebanking)
    - Password       → vía teclado virtual simple-keyboard
  Teclas del teclado: .hg-button[data-skbtn="X"] (simple-keyboard lib).

Post-login: el dashboard de /inicio tiene un link "Tarjetas" que dispara
automáticamente un form POST SSO a tarjetas.bancogalicia.com.ar.

BFF endpoints (llamados via fetch() desde el browser en tarjetas domain):
  GET  https://bff-cards-overview-pota-cards.bff.bancogalicia.com.ar/bff/overview/cards
       → info de tarjeta + settlement_closing_dates {previous, current, next}
  POST https://bff-cards-movements-tc-pota-cards.bff.bancogalicia.com.ar/bff/cards/movements-tc
       → movimientos del período abierto (consumos + cuotas + ajustes + pagos + autorizaciones)

Headers requeridos (auto-set por browser Origin + manual):
  id_channel: onlinebanking

Período-reset:
  settlement_closing_dates.current = fecha de cierre del período vigente.
  Si cambia entre runs (se cerró un nuevo resumen), se borran los movimientos_raw
  de esta fuente y se reimportan solo los del período en curso.

Montos:
  movement_type "credit" / "instalments" → egreso (monto > 0)
  movement_type "payment"                → ingreso (monto < 0)
  Para cuotas: final_amount = monto de ESTA cuota (no el total original).

TOTP:
  En primer login, Galicia puede pedir código de verificación.
  El flujo interactivo (start_session_setup / submit_totp_code) permanece
  igual que en el stub original para compatibilidad con la UI del add-on.
"""

import json as _json
import logging
import os
import threading
import time
import uuid
from datetime import date as _date
from typing import Optional

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_DATA_DIR    = os.environ.get("DATA_DIR", "/data")
_LOGIN_URL   = "https://onlinebanking.bancogalicia.com.ar/login"
_INICIO_URL  = "https://onlinebanking.bancogalicia.com.ar/inicio"
_TARJETAS_URL = "https://tarjetas.bancogalicia.com.ar/tarjetas/ini"

_BFF_OVERVIEW   = "https://bff-cards-overview-pota-cards.bff.bancogalicia.com.ar/bff/overview/cards"
_BFF_MOVEMENTS  = "https://bff-cards-movements-tc-pota-cards.bff.bancogalicia.com.ar/bff/cards/movements-tc"

# Estado global para setups interactivos de TOTP en curso
# {request_id: {"event": threading.Event, "code": str|None, "status": str, "error": str|None}}
_pending_totp: dict[str, dict] = {}

# Archivo de estado para detección de cierre de período
_PERIOD_STATE_PATH = os.path.join(_DATA_DIR, "sessions", "galicia_period_state.json")


def _read_period_state() -> dict:
    try:
        with open(_PERIOD_STATE_PATH) as f:
            return _json.load(f)
    except Exception:
        return {}


def _write_period_state(fuente: str, current_date: str) -> None:
    try:
        state = _read_period_state()
        state[fuente] = current_date
        os.makedirs(os.path.dirname(_PERIOD_STATE_PATH), exist_ok=True)
        with open(_PERIOD_STATE_PATH, "w") as f:
            _json.dump(state, f)
    except Exception as exc:
        logger.warning("[galicia] Error guardando period state: %s", exc)


class GaliciaScraper(BaseScraper):
    fuente        = "galicia"
    nombre        = "Banco Galicia"
    login_origin  = "https://tarjetas.bancogalicia.com.ar"

    # ── BFF helper ────────────────────────────────────────────────────────────

    def _bff_request(
        self,
        driver,
        method: str,
        url: str,
        json_body: dict | None,
        timeout: int = 30,
    ) -> dict:
        """
        Llama a un BFF endpoint de Galicia desde dentro del browser (via fetch).

        Requiere estar en el dominio tarjetas.bancogalicia.com.ar para que las
        cookies de sesión sean enviadas automáticamente.

        Headers enviados:
          - id_channel: onlinebanking  (requerido por los BFF)
          - Origin: seteado automáticamente por el browser (same-origin fetch)
        """
        body_str = _json.dumps(json_body) if json_body is not None else None

        js = """
        var url    = arguments[0];
        var method = arguments[1];
        var body   = arguments[2];
        var cb     = arguments[arguments.length - 1];

        var headers = {
            'Accept':         'application/vnd.iman.v1+json, application/json, */*',
            'id_channel':     'onlinebanking',
            'Cache-Control':  'no-store, no-cache, must-revalidate',
            'Pragma':         'no-cache'
        };
        if (method !== 'GET' && body !== null) {
            headers['Content-Type'] = 'application/json';
        }

        var opts = { method: method, headers: headers, credentials: 'include' };
        if (body !== null) opts.body = body;

        fetch(url, opts)
            .then(function(r) {
                return r.text().then(function(t) {
                    cb({status: r.status, body: t});
                });
            })
            .catch(function(e) {
                cb({status: 0, body: 'fetch error: ' + String(e)});
            });
        """

        try:
            driver.set_script_timeout(timeout + 5)
        except Exception:
            pass

        try:
            result = driver.execute_async_script(js, url, method, body_str)
        except Exception as exc:
            logger.warning("[galicia] _bff_request execute_async_script error: %s", exc)
            return {"status": 0, "body": str(exc), "json": None}

        if not isinstance(result, dict):
            return {"status": 0, "body": str(result), "json": None}

        status = int(result.get("status", 0) or 0)
        body   = str(result.get("body", "") or "")
        parsed = None
        try:
            parsed = _json.loads(body) if body else None
        except Exception:
            pass

        return {"status": status, "body": body, "json": parsed}

    # ── Teclado virtual ───────────────────────────────────────────────────────

    def _type_on_keyboard(self, driver, text: str) -> None:
        """
        Escribe texto usando el teclado virtual simple-keyboard de Galicia.

        Busca botones con selector:  .hg-button[data-skbtn="X"]
        Si no se encuentra el botón, intenta fallback con ActionChains send_keys.
        """
        from selenium.webdriver.common.by import By

        for char in text:
            # Intentar con data-skbtn (simple-keyboard)
            btn = self.find(driver, f'.hg-button[data-skbtn="{char}"]')

            # Fallback: buscar por contenido de texto del botón
            if not btn:
                try:
                    btns = driver.find_elements(By.CSS_SELECTOR, ".hg-button")
                    for b in btns:
                        try:
                            if b.text.strip() == char:
                                btn = b
                                break
                        except Exception:
                            pass
                except Exception:
                    pass

            if btn:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.05)
                    btn.click()
                    time.sleep(0.1)
                except Exception as exc:
                    logger.warning("[galicia] Error clickeando tecla %r: %s", char, exc)
            else:
                logger.warning("[galicia] Tecla %r no encontrada en teclado virtual", char)
                # Fallback: intentar send_keys directamente al elemento activo
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(driver).send_keys(char).perform()
                    time.sleep(0.1)
                except Exception:
                    pass

    # ── Navegar al dashboard de tarjetas ─────────────────────────────────────

    def _navigate_to_tarjetas(self, driver) -> None:
        """
        Navega desde el dashboard principal (/inicio) a tarjetas.bancogalicia.com.ar.

        El click en el link de Tarjetas dispara un form POST SSO automático
        al dominio tarjetas. Esperamos que la URL cambie a tarjetas domain.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException

        # Esperar a que el dashboard esté listo
        time.sleep(2)

        # Intentar varios selectores para el link de Tarjetas
        el = None
        for sel in [
            "a[href*='tarjetas.bancogalicia']",
            "a[href*='/Tarjetas']",
            "a[href*='OverviewTC']",
            ".menu-tarjetas a",
            ".nav-tarjetas",
            "#lnkTarjetas",
        ]:
            el = self.find(driver, sel)
            if el:
                logger.info("[galicia] Link tarjetas encontrado con selector: %s", sel)
                break

        # Fallback: buscar por texto
        if not el:
            for partial_text in ["Tarjetas", "tarjetas", "TARJETAS"]:
                try:
                    els = driver.find_elements(By.PARTIAL_LINK_TEXT, partial_text)
                    if els:
                        el = els[0]
                        logger.info("[galicia] Link tarjetas por texto: %r", partial_text)
                        break
                except Exception:
                    pass

        if not el:
            # Último recurso: loguear la estructura del nav para diagnóstico
            try:
                links = driver.find_elements(By.CSS_SELECTOR, "a")
                logger.info("[galicia] Links en /inicio (%d):", len(links))
                for lnk in links[:20]:
                    href  = lnk.get_attribute("href") or ""
                    texto = (lnk.text or "").strip()[:40]
                    if href or texto:
                        logger.info("[galicia]   href=%r texto=%r", href[:80], texto)
            except Exception:
                pass
            raise RuntimeError(
                "[galicia] No se encontró el link de Tarjetas en el dashboard. "
                "Verificar selectores o estructura del HTML."
            )

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.3)
        el.click()

        # Esperar que la URL cambie a tarjetas domain
        try:
            WebDriverWait(driver, 30).until(
                lambda d: "tarjetas.bancogalicia.com.ar" in (d.current_url or "")
            )
        except TimeoutException:
            cur = driver.current_url or ""
            raise RuntimeError(
                f"[galicia] Timeout esperando tarjetas domain. URL actual: {cur[:200]}"
            )

        time.sleep(3)  # Esperar inicialización del SPA
        logger.info("[galicia] Navegación a tarjetas OK: %s", driver.current_url[:100])

    # ── check_session ─────────────────────────────────────────────────────────

    def check_session(self, driver) -> bool:
        """
        Verifica que la sesión de tarjetas siga activa llamando al BFF overview.
        La sesión se restaura en tarjetas.bancogalicia.com.ar (login_origin).
        """
        try:
            # Asegurar que estamos en tarjetas domain antes de hacer fetch
            cur = driver.current_url or ""
            if "tarjetas.bancogalicia.com.ar" not in cur:
                driver.get("https://tarjetas.bancogalicia.com.ar/")
                time.sleep(2)

            resp = self._bff_request(driver, "GET", _BFF_OVERVIEW, None)
            logger.info("[galicia] check_session HTTP %d", resp["status"])
            return resp["status"] == 200
        except Exception as exc:
            logger.debug("[galicia] check_session error: %s", exc)
            return False

    # ── do_login ──────────────────────────────────────────────────────────────

    def do_login(self, driver, config: dict) -> None:
        """
        Login completo: main banking → navegar a tarjetas.

        1. GET /login → rellena formulario con DNI + usuario + teclado virtual
        2. Espera /inicio
        3. Click en link Tarjetas → SSO → tarjetas.bancogalicia.com.ar
        """
        from selenium.webdriver.support.ui import WebDriverWait

        dni      = str(config.get("usuario", "")).strip()
        username = str(config.get("tercer_dato", "")).strip()
        password = str(config.get("password", "")).strip()

        if not dni or not password:
            raise RuntimeError("[galicia] Credenciales incompletas: se requieren usuario (DNI) y password")

        # ── Paso 1: cargar página de login ────────────────────────────────────
        logger.info("[galicia] Cargando página de login: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        time.sleep(3)

        # Esperar que aparezca el formulario
        try:
            self.wait_for(driver, "input, .keyboard-container, .simple-keyboard", timeout=15)
        except Exception:
            logger.info("[galicia] Timeout esperando formulario, continuando…")

        # ── Paso 2: campo DocumentNumber (DNI) ───────────────────────────────
        doc_input = None
        for sel in [
            "input[name='DocumentNumber']",
            "input#DocumentNumber",
            "input[id*='document' i]",
            "input[placeholder*='DNI' i]",
            "input[placeholder*='documento' i]",
            "input[type='number']",
            "input[type='tel']",
        ]:
            doc_input = self.find(driver, sel)
            if doc_input:
                logger.info("[galicia] Input DNI encontrado: %s", sel)
                break

        if doc_input:
            try:
                doc_input.clear()
                doc_input.send_keys(dni)
                time.sleep(0.3)
            except Exception as exc:
                logger.warning("[galicia] Error escribiendo DNI: %s", exc)
        else:
            logger.warning("[galicia] Input DNI no encontrado — continuando sin él")

        # ── Paso 3: campo UserName (alias) ────────────────────────────────────
        if username:
            user_input = None
            for sel in [
                "input[name='UserName']",
                "input#UserName",
                "input[id*='user' i]",
                "input[name*='user' i]",
                "input[placeholder*='usuario' i]",
                "input[autocomplete='username']",
            ]:
                user_input = self.find(driver, sel)
                if user_input:
                    logger.info("[galicia] Input usuario encontrado: %s", sel)
                    break

            if user_input:
                try:
                    user_input.clear()
                    user_input.send_keys(username)
                    time.sleep(0.3)
                except Exception as exc:
                    logger.warning("[galicia] Error escribiendo usuario: %s", exc)

        # ── Paso 4: contraseña vía teclado virtual ────────────────────────────
        # Primero hacer clic en el campo de password para activar el teclado
        pass_input = None
        for sel in [
            "input[name='Password']",
            "input#Password",
            "input[type='password']",
            ".password-input",
        ]:
            pass_input = self.find(driver, sel)
            if pass_input:
                logger.info("[galicia] Input password encontrado: %s", sel)
                break

        if pass_input:
            try:
                pass_input.click()
                time.sleep(0.5)  # Esperar que aparezca el teclado virtual
            except Exception:
                pass

        # Verificar si hay teclado virtual
        keyboard_present = self.find(driver, ".simple-keyboard, .hg-button") is not None
        logger.info("[galicia] Teclado virtual presente: %s", keyboard_present)

        if keyboard_present:
            self._type_on_keyboard(driver, password)
        elif pass_input:
            # Fallback: send_keys directo
            try:
                pass_input.clear()
                pass_input.send_keys(password)
            except Exception as exc:
                logger.warning("[galicia] Error escribiendo password: %s", exc)

        time.sleep(0.5)

        # ── Paso 5: submit ────────────────────────────────────────────────────
        submit = None
        for sel in [
            "button[type='submit']",
            "input[type='submit']",
            "button.btn-ingresar",
            "button.btn-primary",
            ".btn-login",
        ]:
            submit = self.find(driver, sel)
            if submit:
                logger.info("[galicia] Botón submit encontrado: %s", sel)
                break

        if not submit:
            # Buscar por texto del botón
            from selenium.webdriver.common.by import By
            for txt in ["Ingresar", "ingresar", "INGRESAR", "Entrar"]:
                try:
                    els = driver.find_elements(By.XPATH, f"//button[contains(text(),'{txt}')]")
                    if els:
                        submit = els[0]
                        break
                except Exception:
                    pass

        if submit:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
                time.sleep(0.2)
                submit.click()
                logger.info("[galicia] Submit clickeado")
            except Exception as exc:
                raise RuntimeError(f"[galicia] Error clickeando submit: {exc}")
        else:
            # Intentar submit por Enter en el campo password
            logger.warning("[galicia] Botón submit no encontrado — intentando Enter")
            if pass_input:
                from selenium.webdriver.common.keys import Keys
                try:
                    pass_input.send_keys(Keys.RETURN)
                except Exception:
                    pass

        # ── Paso 6: esperar /inicio ───────────────────────────────────────────
        from selenium.common.exceptions import TimeoutException

        try:
            WebDriverWait(driver, 45).until(
                lambda d: (
                    "/inicio" in (d.current_url or "")
                    or "/Navigation/MenuLink" in (d.current_url or "")
                )
            )
        except TimeoutException:
            cur = driver.current_url or ""
            # Verificar si apareció pantalla de TOTP
            if self.find(driver, "input[maxlength='6'], .otp-input, #otpCode, .totp"):
                raise _SessionNeedsTotp(
                    "Galicia requiere código de verificación (TOTP). "
                    "Usá 'Configurar sesión Galicia' en la UI del add-on."
                )
            # Verificar si seguimos en login (credenciales incorrectas)
            if "/login" in cur or "Users/LogIn" in cur:
                self._dump_page(driver)
                raise RuntimeError(
                    f"[galicia] Seguimos en la pantalla de login tras el submit. "
                    f"URL: {cur[:200]}. Verificar credenciales."
                )
            raise RuntimeError(f"[galicia] Timeout esperando /inicio. URL: {cur[:200]}")

        logger.info("[galicia] Login OK — URL: %s", driver.current_url[:100])
        time.sleep(2)

        # ── Paso 7: navegar a Tarjetas ────────────────────────────────────────
        self._navigate_to_tarjetas(driver)

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[galicia] %s", msg)
            log.append(msg)

        # Asegurar que estamos en tarjetas domain
        cur = driver.current_url or ""
        if "tarjetas.bancogalicia.com.ar" not in cur:
            _log("Navegando a tarjetas desde scrape()…")
            self._navigate_to_tarjetas(driver)

        # ── Obtener info de tarjetas y período ────────────────────────────────
        _log("Llamando BFF overview/cards…")
        ov_resp = self._bff_request(driver, "GET", _BFF_OVERVIEW, None)
        if ov_resp["status"] != 200:
            raise RuntimeError(
                f"[galicia] BFF overview HTTP {ov_resp['status']}: {ov_resp['body'][:200]}"
            )

        ov_data = (ov_resp["json"] or {}).get("data", [])
        if not ov_data:
            raise RuntimeError("[galicia] BFF overview: data vacía")

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # Determinar fuente target (multi-instancia)
        fuente_target = self._fuente_for_product(config, "main", "galicia_mc")

        # Procesar cada grupo de tarjetas
        for grupo in ov_data:
            credit_cards = grupo.get("credit_cards") or []
            for card in credit_cards:
                movs, saldo = self._scrape_card(driver, card, fuente_target, _log)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos.setdefault(fuente_target, {})["saldo_ars"] = saldo

        _log(f"Total movimientos encontrados: {len(movimientos)}")
        return ScraperResult(
            fuente      = "galicia",
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    def _scrape_card(
        self,
        driver,
        card: dict,
        fuente_target: str,
        log_fn,
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Obtiene movimientos de una tarjeta de crédito Galicia.

        Maneja el período-reset: si settlement_closing_dates.current cambió,
        borra todos los movimientos_raw de la fuente antes de insertar los nuevos.
        """
        account_number = card.get("account_number") or ""
        last_four      = card.get("last_digits") or ""
        brand          = (card.get("brand") or "MASTER").upper()
        product        = card.get("product") or ""

        log_fn(f"Tarjeta: {brand} *{last_four} — cuenta {account_number} ({product})")

        # ── Período: determinar rango y detectar reset ────────────────────────
        closing = card.get("settlement_closing_dates") or {}
        current_close = closing.get("current") or ""
        next_close    = closing.get("next")    or ""

        log_fn(f"Período actual: cierra {current_close}, próximo cierra {next_close}")

        if current_close and next_close:
            stored_state = _read_period_state()
            stored_close = stored_state.get(fuente_target)

            if stored_close and stored_close != current_close:
                log_fn(
                    f"[PERÍODO RESET] Cierre cambió: {stored_close} → {current_close}. "
                    f"Borrando movimientos_raw de {fuente_target}…"
                )
                self._delete_movimientos_raw(fuente_target, log_fn)

            _write_period_state(fuente_target, current_close)

            date_from = current_close
            date_to   = next_close
        else:
            log_fn("No se obtuvieron fechas de cierre — usando período abierto sin fecha")
            date_from = ""
            date_to   = ""

        # ── Consumo total (saldo) ─────────────────────────────────────────────
        saldo = None
        consumptions_summary = card.get("consumption") or []
        for c in consumptions_summary:
            if (c.get("currency") or "").upper() == "ARS":
                saldo = float(c.get("total_amount") or 0)
                break

        # ── Llamar BFF movimientos ────────────────────────────────────────────
        payload: dict = {
            "credit_account_number":      account_number,
            "brand":                      brand[:6].upper() if brand.startswith("MASTER") else brand[:4].upper(),
            "card_number_last_four_digits": last_four,
            "is_additional":              False,
            "type":                       "open",
            "movement_type":              ["CONSUMPTION", "ADJUSTMENT", "PAYMENT", "AUTHORIZATION"],
        }
        if date_from and date_to:
            payload["date_from"] = date_from
            payload["date_to"]   = date_to

        log_fn(f"Llamando BFF movements-tc (from={date_from} to={date_to})…")
        mv_resp = self._bff_request(driver, "POST", _BFF_MOVEMENTS, payload)

        if mv_resp["status"] != 200:
            log_fn(f"BFF movements HTTP {mv_resp['status']}: {mv_resp['body'][:200]}")
            return [], saldo

        mv_data = (mv_resp["json"] or {}).get("data", [])
        if not mv_data:
            log_fn("BFF movements: data vacía")
            return [], saldo

        # La respuesta es un array con un único elemento que contiene las listas
        result_block = mv_data[0] if mv_data else {}
        movs = self._parse_movements(result_block, fuente_target, log_fn)

        return movs, saldo

    @staticmethod
    def _delete_movimientos_raw(fuente: str, log_fn) -> None:
        """Borra todos los movimientos_raw de la fuente (período reset)."""
        try:
            from scrapers_db import _conn
            with _conn() as conn:
                deleted = conn.execute(
                    "DELETE FROM movimientos_raw WHERE fuente = ?", (fuente,)
                ).rowcount
            log_fn(f"[PERÍODO RESET] {deleted} movimientos_raw de {fuente} borrados")
        except Exception as exc:
            log_fn(f"[PERÍODO RESET] Error borrando movimientos_raw: {exc}")
            logger.error("[galicia] Error en período reset: %s", exc)

    def _parse_movements(
        self,
        block: dict,
        fuente_target: str,
        log_fn,
    ) -> list[MovimientoRaw]:
        """
        Convierte la respuesta del BFF movements-tc a MovimientoRaw.

        Estructura del bloque:
          consumptions[]     → consumos y cuotas (movement_type: "credit" / "instalments")
          adjustments[]      → ajustes
          payments[]         → pagos al resumen
          authorizations[]   → pre-autorizaciones (todavía no procesadas)

        Convención de monto:
          monto > 0 = egreso    (lo que gastás)
          monto < 0 = ingreso   (crédito / pago recibido)
        """
        result: list[MovimientoRaw] = []

        # Consumos (compras en 1 pago y cuotas)
        consumptions = block.get("consumptions") or []
        for c in consumptions:
            mov = self._parse_consumption(c, fuente_target)
            if mov:
                result.append(mov)
                log_fn(f"  consumo: {mov.fecha}  {mov.descripcion[:50]}  {mov.monto:+.2f}")

        # Ajustes
        adjustments = block.get("adjustments") or []
        for a in adjustments:
            mov = self._parse_adjustment(a, fuente_target)
            if mov:
                result.append(mov)
                log_fn(f"  ajuste: {mov.fecha}  {mov.descripcion[:50]}  {mov.monto:+.2f}")

        # Pagos (créditos al resumen)
        payments = block.get("payments") or []
        for p in payments:
            mov = self._parse_payment(p, fuente_target)
            if mov:
                result.append(mov)
                log_fn(f"  pago: {mov.fecha}  {mov.descripcion[:50]}  {mov.monto:+.2f}")

        # Autorizaciones (pendientes de procesamiento)
        authorizations = block.get("authorizations") or []
        for a in authorizations:
            mov = self._parse_authorization(a, fuente_target)
            if mov:
                result.append(mov)
                log_fn(f"  autorización: {mov.fecha}  {mov.descripcion[:50]}  {mov.monto:+.2f}")

        log_fn(
            f"Total: {len(consumptions)} consumos, {len(adjustments)} ajustes, "
            f"{len(payments)} pagos, {len(authorizations)} autorizaciones → "
            f"{len(result)} MovimientoRaw"
        )
        return result

    @staticmethod
    def _parse_consumption(c: dict, fuente: str) -> Optional[MovimientoRaw]:
        """
        Parsea un consumo o cuota del BFF.

        Para cuotas: final_amount es el valor de ESTA cuota (no el total original).
        Descripción: "MERCHANT_NAME 2/6" para cuotas, "MERCHANT_NAME" para pago único.
        """
        fecha = c.get("transaction_date") or c.get("submission_date") or ""
        if not fecha:
            return None

        merchant = (c.get("merchant_name") or "").strip()
        plan     = int(c.get("installment_plan")   or 0)
        numero   = int(c.get("installment_number") or 0)
        amount   = float(c.get("final_amount") or c.get("transaction_amount") or 0)
        moneda   = (c.get("final_currency") or c.get("transaction_currency") or "ARS").upper()
        mv_type  = (c.get("movement_type") or "credit").lower()

        if not merchant:
            merchant = "Consumo Galicia"

        # Descripción con número de cuota si aplica
        if plan > 0 and numero > 0:
            desc = f"{merchant} {numero}/{plan}"
        else:
            desc = merchant

        # Signo: pagos son ingresos (monto < 0), consumos son egresos (monto > 0)
        # movement_type "credit" = compra/cargo
        # movement_type "instalments" = cuota de compra en cuotas
        monto = amount  # > 0 = egreso (ya está en positivo)

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha,
            descripcion = desc,
            monto       = monto,
            moneda      = moneda,
            raw_data    = {
                "receipt_number":      c.get("receipt_number"),
                "auth_code":           c.get("auth_code"),
                "transaction_amount":  c.get("transaction_amount"),
                "final_amount":        c.get("final_amount"),
                "installment_plan":    plan or None,
                "installment_number":  numero or None,
                "movement_type":       mv_type,
                "operation_type":      c.get("operation_type"),
                "submission_date":     c.get("submission_date"),
                "last_four_digits":    c.get("last_four_digits"),
            },
        )

    @staticmethod
    def _parse_adjustment(a: dict, fuente: str) -> Optional[MovimientoRaw]:
        """Parsea un ajuste/devolución del resumen."""
        fecha  = a.get("transaction_date") or a.get("date") or ""
        if not fecha:
            return None
        desc   = (a.get("description") or a.get("merchant_name") or "Ajuste").strip()
        amount = float(a.get("amount") or a.get("final_amount") or 0)
        moneda = (a.get("currency") or a.get("final_currency") or "ARS").upper()

        # Ajustes negativos son créditos (ej. devolución)
        monto = amount

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha,
            descripcion = f"Ajuste: {desc}",
            monto       = monto,
            moneda      = moneda,
            raw_data    = dict(a),
        )

    @staticmethod
    def _parse_payment(p: dict, fuente: str) -> Optional[MovimientoRaw]:
        """Parsea un pago al resumen (crédito)."""
        fecha  = p.get("transaction_date") or p.get("date") or ""
        if not fecha:
            return None
        amount = float(p.get("amount") or p.get("final_amount") or 0)
        moneda = (p.get("currency") or p.get("final_currency") or "ARS").upper()
        desc   = (p.get("description") or "Pago Galicia").strip()

        # Pago = ingreso = monto negativo
        monto = -abs(amount)

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha,
            descripcion = desc,
            monto       = monto,
            moneda      = moneda,
            raw_data    = dict(p),
        )

    @staticmethod
    def _parse_authorization(a: dict, fuente: str) -> Optional[MovimientoRaw]:
        """
        Parsea una pre-autorización (todavía no procesada).
        Se incluye para visibilidad, pero podría deduplicarse con el consumo
        cuando se confirma.
        """
        fecha  = (a.get("transaction_date") or "")[:10]  # solo YYYY-MM-DD
        if not fecha:
            return None
        merchant = (a.get("merchant_name") or "Autorización").strip()
        amount   = float(a.get("amount") or a.get("transaction_amount") or 0)
        moneda   = (a.get("currency") or a.get("transaction_currency") or "ARS").upper()

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha,
            descripcion = f"[Auth] {merchant}",
            monto       = float(amount),
            moneda      = moneda,
            raw_data    = {
                "merchant_number": a.get("merchant_number"),
                "auth_code":       a.get("authorization_code"),
                "type":            a.get("type"),
                "channel":         a.get("channel"),
                "status":          a.get("transaction_status"),
                "is_authorization": True,
            },
        )

    # ── Diagnóstico ───────────────────────────────────────────────────────────

    def _dump_page(self, driver) -> None:
        """Loguea información diagnóstica de la página actual."""
        try:
            logger.info("[galicia-diag] URL: %s", driver.current_url or "?")
            logger.info("[galicia-diag] Título: %r", driver.title or "?")
            body = driver.execute_script(
                "return document.body ? document.body.innerHTML.slice(0,600) : '(sin body)'"
            )
            logger.info("[galicia-diag] body[:600]: %s", body)
        except Exception as exc:
            logger.info("[galicia-diag] error: %s", exc)

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
            time.sleep(3)

            # Rellenar formulario igual que do_login
            dni      = str(config.get("usuario", "")).strip()
            username = str(config.get("tercer_dato", "")).strip()
            password = str(config.get("password", "")).strip()

            for sel, value in [
                ("input[name='DocumentNumber'], input[type='number']", dni),
                ("input[name='UserName'], input[id*='user' i]", username if username else None),
            ]:
                if value is None:
                    continue
                el = self.find(driver, sel)
                if el:
                    el.clear()
                    el.send_keys(value)
                    time.sleep(0.3)

            # Contraseña vía teclado virtual
            pass_input = self.find(driver, "input[name='Password'], input[type='password']")
            if pass_input:
                pass_input.click()
                time.sleep(0.5)

            if self.find(driver, ".simple-keyboard, .hg-button"):
                self._type_on_keyboard(driver, password)
            elif pass_input:
                pass_input.clear()
                pass_input.send_keys(password)

            # Submit
            submit = self.find(driver, "button[type='submit']")
            if submit:
                submit.click()

            # ── Esperar pantalla TOTP ──────────────────────────────────────────
            totp_input = self.wait_for(
                driver,
                "input[maxlength='6'], .otp-input, #otpCode, .totp input",
                timeout=30,
            )
            logger.info("[galicia_setup] Pantalla TOTP detectada, esperando código…")
            entry["status"] = "waiting_code"

            # Esperar código del usuario (5 min timeout)
            got_code = entry["event"].wait(timeout=300)
            if not got_code:
                entry["status"] = "timeout"
                entry["error"]  = "Timeout esperando el código TOTP"
                return

            code = entry["code"]
            if not code:
                entry["error"] = "Código vacío"
                return

            # Ingresar código
            totp_input.clear()
            totp_input.send_keys(code)
            time.sleep(0.5)

            # Checkbox "recordar este dispositivo"
            remember = self.find(
                driver,
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

            # Confirmar TOTP
            confirm = self.find(
                driver,
                "button[type='submit'], button.btn-confirmar"
            )
            if confirm:
                confirm.click()

            # Esperar dashboard
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(driver, 30).until(
                lambda d: "/inicio" in (d.current_url or "")
            )

            # Navegar a tarjetas para establecer esas cookies también
            try:
                self._navigate_to_tarjetas(driver)
            except Exception as nav_exc:
                logger.warning("[galicia_setup] No se pudo navegar a tarjetas: %s", nav_exc)

            # Guardar sesión (tarjetas domain)
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
            threading.Timer(300, lambda: _pending_totp.pop(request_id, None)).start()


class _SessionNeedsTotp(Exception):
    """Indica que el login automático requiere TOTP interactivo."""

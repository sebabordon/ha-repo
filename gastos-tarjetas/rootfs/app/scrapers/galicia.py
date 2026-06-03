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

    # ── Driver con interceptor de fetch ───────────────────────────────────────

    def _create_driver(self):
        """
        Crea el WebDriver e inyecta un proxy de window.fetch via CDP que captura
        todas las respuestas a *.bff.bancogalicia.com.ar en window.__galiciaBff.

        Esto permite que la SPA de tarjetas haga sus propias llamadas BFF
        (con las cookies y el contexto correcto) y nosotros leamos los datos
        capturados, evitando completamente los problemas de CORS.
        """
        driver = super()._create_driver()
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    window.__galiciaBff = {};
                    (function() {
                        // ── Proxy fetch ────────────────────────────────────────
                        var _origFetch = window.fetch;
                        window.fetch = function() {
                            var args = arguments;
                            var url  = args[0];
                            var urlStr = (typeof url === 'string') ? url
                                         : (url && url.url) ? url.url : String(url);
                            var p = _origFetch.apply(window, args);
                            if (urlStr.indexOf('.bff.bancogalicia') >= 0) {
                                p.then(function(r) {
                                    r.clone().text().then(function(t) {
                                        window.__galiciaBff[urlStr] = t;
                                    });
                                }).catch(function(){});
                            }
                            return p;
                        };

                        // ── Proxy XMLHttpRequest (axios/jQuery usan XHR) ───────
                        var _origOpen = XMLHttpRequest.prototype.open;
                        var _origSend = XMLHttpRequest.prototype.send;
                        XMLHttpRequest.prototype.open = function(method, url) {
                            this._galiciaUrl = String(url || '');
                            return _origOpen.apply(this, arguments);
                        };
                        XMLHttpRequest.prototype.send = function() {
                            var xhr = this;
                            if (xhr._galiciaUrl &&
                                xhr._galiciaUrl.indexOf('.bff.bancogalicia') >= 0) {
                                xhr.addEventListener('load', function() {
                                    if (xhr.readyState === 4) {
                                        window.__galiciaBff[xhr._galiciaUrl] = xhr.responseText;
                                    }
                                });
                            }
                            return _origSend.apply(this, arguments);
                        };
                    })();
                """
            })
        except Exception as exc:
            logger.warning("[galicia] No se pudo inyectar interceptor fetch: %s", exc)
        return driver

    # ── Lectura de datos BFF capturados ──────────────────────────────────────

    def _wait_for_bff_capture(
        self,
        driver,
        keys: list[str],
        timeout_secs: int = 15,
    ) -> dict[str, dict]:
        """
        Espera hasta timeout_secs a que window.__galiciaBff contenga respuestas
        para todas las URLs que contengan alguno de los strings en `keys`.

        Devuelve {key_string: parsed_json} para cada clave encontrada.
        """
        import time as _t
        deadline = _t.time() + timeout_secs
        while _t.time() < deadline:
            raw = driver.execute_script(
                "return window.__galiciaBff ? JSON.stringify(window.__galiciaBff) : '{}'"
            ) or "{}"
            captured = _json.loads(raw)
            found = {}
            for k in keys:
                for url, body in captured.items():
                    if k in url:
                        try:
                            found[k] = _json.loads(body)
                        except Exception:
                            found[k] = None
                        break
            if all(k in found for k in keys):
                return found
            _t.sleep(0.8)
        # Retornar lo que hay aunque no esté completo
        raw = driver.execute_script(
            "return window.__galiciaBff ? JSON.stringify(window.__galiciaBff) : '{}'"
        ) or "{}"
        captured = _json.loads(raw)
        result = {}
        for k in keys:
            for url, body in captured.items():
                if k in url:
                    try:
                        result[k] = _json.loads(body)
                    except Exception:
                        result[k] = None
                    break
        return result

    def _reset_bff_capture(self, driver) -> None:
        """Limpia el buffer de capturas (útil entre runs o para forzar recarga)."""
        try:
            driver.execute_script("window.__galiciaBff = {};")
        except Exception:
            pass

    # ── BFF helper (fallback directo) ─────────────────────────────────────────

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

        # Solo id_channel es necesario; Cache-Control/Pragma rompen el CORS preflight
        # porque algunos servidores no los listan en Access-Control-Allow-Headers.
        js = """
        var url    = arguments[0];
        var method = arguments[1];
        var body   = arguments[2];
        var cb     = arguments[arguments.length - 1];

        var headers = {
            'Accept':     'application/vnd.iman.v1+json, application/json, */*',
            'id_channel': 'onlinebanking'
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
                cb({
                    status: 0,
                    body: 'fetch error: ' + e.name + ': ' + e.message
                         + ' | page=' + window.location.href
                         + ' | url=' + url
                });
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

        Busca botones con selector .hg-button[data-skbtn="X"] (simple-keyboard lib).
        Si no lo encuentra, busca el botón por contenido de texto.
        """
        from selenium.webdriver.common.by import By

        hits = 0
        misses = 0
        for char in text:
            btn = self.find(driver, f'.hg-button[data-skbtn="{char}"]')

            if not btn:
                # Fallback: buscar por texto del botón
                try:
                    for b in driver.find_elements(By.CSS_SELECTOR, ".hg-button"):
                        if (b.text or "").strip() == char:
                            btn = b
                            break
                except Exception:
                    pass

            if btn:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.05)
                    btn.click()
                    time.sleep(0.12)
                    hits += 1
                except Exception as exc:
                    logger.warning("[galicia-kbd] Error clickeando tecla %r: %s", char, exc)
                    misses += 1
            else:
                logger.warning("[galicia-kbd] Tecla %r NO encontrada en teclado", char)
                misses += 1
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(driver).send_keys(char).perform()
                    time.sleep(0.1)
                except Exception:
                    pass

        logger.info("[galicia-kbd] Teclado: %d teclas OK, %d no encontradas", hits, misses)

    def _type_on_keyboard_generic(self, driver, text: str, btns: list) -> None:
        """
        Fallback para teclados con estructura diferente a simple-keyboard.
        Itera los botones buscando coincidencia de texto.
        """
        for char in text:
            found = False
            for b in btns:
                try:
                    if (b.text or "").strip() == char:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                        time.sleep(0.05)
                        b.click()
                        time.sleep(0.12)
                        found = True
                        break
                except Exception:
                    pass
            if not found:
                logger.warning("[galicia-kbd] Tecla genérica %r no encontrada", char)

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
        Verifica la sesión: navega a /tarjetas/ini via SSO desde el dashboard
        y espera que la SPA llame al BFF overview.
        """
        try:
            # Navegar via SSO para que la SPA tenga contexto de autenticación
            cur = driver.current_url or ""
            if "onlinebanking.bancogalicia.com.ar" not in cur:
                driver.get(_INICIO_URL)
                time.sleep(3)

            self._reset_bff_capture(driver)
            self._navigate_to_tarjetas(driver)

            captured = self._wait_for_bff_capture(driver, ["overview/cards"], timeout_secs=15)
            ok = bool(captured.get("overview/cards"))
            logger.info("[galicia] check_session: overview capturado=%s", ok)
            return ok
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
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import TimeoutException

        dni      = str(config.get("usuario", "")).strip()
        username = str(config.get("tercer_dato", "")).strip()
        password = str(config.get("password", "")).strip()

        if not dni or not password:
            raise RuntimeError("[galicia] Credenciales incompletas: se requieren usuario (DNI) y password")

        # ── Paso 1: cargar página de login ────────────────────────────────────
        logger.info("[galicia] Paso 1 — cargando login: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)

        # Esperar que aparezcan inputs (el JS puede tardar hasta ~8s)
        for wait_secs in [3, 6, 10]:
            time.sleep(wait_secs)
            if driver.find_elements(By.CSS_SELECTOR, "input"):
                logger.info("[galicia] Inputs detectados después de %ds", wait_secs)
                break
        else:
            logger.info("[galicia] No se detectaron inputs tras 10s")

        # Dump diagnóstico de la página de login
        self._dump_form_structure(driver)

        # ── Paso 2: campo DocumentNumber (DNI) ───────────────────────────────
        logger.info("[galicia] Paso 2 — buscando campo DNI")
        doc_input = None
        for sel in [
            "input[name='DocumentNumber']",
            "input#DocumentNumber",
            "input[id*='document' i]",
            "input[placeholder*='DNI' i]",
            "input[placeholder*='documento' i]",
            "input[placeholder*='Documento' i]",
            "input[type='number']",
            "input[type='tel']",
        ]:
            doc_input = self.find(driver, sel)
            if doc_input:
                logger.info("[galicia] Input DNI encontrado con selector: %s", sel)
                break

        if doc_input:
            try:
                doc_input.clear()
                doc_input.send_keys(dni)
                logger.info("[galicia] DNI escrito OK (%d dígitos)", len(dni))
                time.sleep(0.3)
            except Exception as exc:
                logger.warning("[galicia] Error escribiendo DNI: %s", exc)
        else:
            logger.warning("[galicia] *** Input DNI NO encontrado — formulario puede fallar ***")

        # ── Paso 3: campo UserName (alias) ────────────────────────────────────
        logger.info("[galicia] Paso 3 — buscando campo usuario (alias=%r)", username or "(vacío)")
        if username:
            user_input = None
            for sel in [
                "input[name='UserName']",
                "input#UserName",
                "input[id*='user' i]",
                "input[name*='user' i]",
                "input[placeholder*='usuario' i]",
                "input[placeholder*='Usuario' i]",
                "input[autocomplete='username']",
                "input[type='text']",
            ]:
                user_input = self.find(driver, sel)
                if user_input and user_input != doc_input:
                    logger.info("[galicia] Input usuario encontrado con selector: %s", sel)
                    break

            if user_input:
                try:
                    user_input.clear()
                    user_input.send_keys(username)
                    logger.info("[galicia] Alias escrito OK")
                    time.sleep(0.3)
                except Exception as exc:
                    logger.warning("[galicia] Error escribiendo alias: %s", exc)
            else:
                logger.warning("[galicia] Input usuario no encontrado")
        else:
            logger.info("[galicia] Sin alias configurado (tercer_dato vacío) — saltando campo usuario")

        # ── Paso 4: contraseña — send_keys directo (el campo acepta teclado normal) ──
        logger.info("[galicia] Paso 4 — buscando campo password")

        pass_input = None
        for sel in [
            "input[name='Password']",
            "input#Password",
            "input[type='password']",
            ".password-input input",
            ".password-input",
        ]:
            pass_input = self.find(driver, sel)
            if pass_input:
                logger.info("[galicia] Input password encontrado con selector: %s", sel)
                break

        # Dump diagnóstico del teclado (para logging, no determina la estrategia)
        self._dump_keyboard_structure(driver)

        if pass_input:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", pass_input)
                time.sleep(0.2)
                pass_input.click()
                time.sleep(0.3)
                pass_input.clear()
                pass_input.send_keys(password)
                logger.info("[galicia] Password escrito vía send_keys (%d chars)", len(password))
            except Exception as exc:
                logger.warning("[galicia] Error escribiendo password con send_keys: %s — intentando teclado virtual", exc)
                # Fallback: teclado virtual por si send_keys no dispara el evento correcto
                hg_btns = driver.find_elements(By.CSS_SELECTOR, ".hg-button")
                if hg_btns:
                    logger.info("[galicia] Fallback a teclado virtual (%d botones)", len(hg_btns))
                    self._type_on_keyboard(driver, password)
        else:
            logger.warning("[galicia] *** Campo password NO encontrado — intentando teclado virtual ***")
            hg_btns = driver.find_elements(By.CSS_SELECTOR, ".hg-button")
            if hg_btns:
                self._type_on_keyboard(driver, password)
            else:
                logger.warning("[galicia] *** Sin campo password NI teclado virtual — contraseña no ingresada ***")

        time.sleep(0.5)

        # ── Paso 5: submit ────────────────────────────────────────────────────
        logger.info("[galicia] Paso 5 — buscando botón submit")
        submit = None
        for sel in [
            "button[type='submit']",
            "input[type='submit']",
            "button.btn-ingresar",
            "button.btn-primary",
            "button.btn-login",
            ".btn-login",
            "form button:last-of-type",
        ]:
            submit = self.find(driver, sel)
            if submit:
                logger.info("[galicia] Botón submit encontrado con selector: %s  texto=%r",
                            sel, (submit.text or "").strip()[:40])
                break

        if not submit:
            for txt in ["Ingresar", "ingresar", "INGRESAR", "Entrar", "entrar"]:
                try:
                    els = driver.find_elements(By.XPATH, f"//button[contains(text(),'{txt}')]")
                    if els:
                        submit = els[0]
                        logger.info("[galicia] Botón submit encontrado por texto: %r", txt)
                        break
                except Exception:
                    pass

        if submit:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
                time.sleep(0.3)
                submit.click()
                logger.info("[galicia] Submit clickeado — esperando navegación a /inicio…")
            except Exception as exc:
                raise RuntimeError(f"[galicia] Error clickeando submit: {exc}")
        else:
            logger.warning("[galicia] *** Botón submit no encontrado — enviando Enter ***")
            if pass_input:
                from selenium.webdriver.common.keys import Keys
                try:
                    pass_input.send_keys(Keys.RETURN)
                except Exception:
                    pass

        # ── Paso 6: esperar /inicio o detectar TOTP ───────────────────────────
        logger.info("[galicia] Paso 6 — esperando resultado del submit (hasta 45s)…")

        try:
            WebDriverWait(driver, 45).until(
                lambda d: (
                    "/inicio" in (d.current_url or "")
                    or "/Navigation/MenuLink" in (d.current_url or "")
                    or "tarjetas.bancogalicia.com.ar" in (d.current_url or "")
                )
            )
        except TimeoutException:
            cur = driver.current_url or ""
            logger.info("[galicia] Timeout — URL actual: %s", cur[:200])

            # Detectar TOTP con múltiples selectores
            totp_selectors = [
                "input[maxlength='6']",
                ".otp-input",
                "#otpCode",
                ".totp",
                "input[name*='token' i]",
                "input[name*='code' i]",
                "input[name*='otp' i]",
                "[class*='verification']",
                "[class*='token']",
            ]
            for totp_sel in totp_selectors:
                if self.find(driver, totp_sel):
                    logger.info("[galicia] Pantalla TOTP detectada (selector: %s)", totp_sel)
                    self._dump_form_structure(driver)
                    raise _SessionNeedsTotp(
                        "Galicia requiere código de verificación (TOTP / segundo factor). "
                        "Usá 'Configurar sesión Galicia' en la UI del add-on."
                    )

            # Seguimos en la pantalla de login → dumpe y error
            self._dump_form_structure(driver)
            self._dump_keyboard_structure(driver)

            if "/login" in cur or "Users/LogIn" in cur:
                raise RuntimeError(
                    f"[galicia] Sigue en pantalla de login tras submit (URL: {cur[:200]}). "
                    f"Causas posibles: (1) EncriptedPassword vacío — teclado virtual no "
                    f"encontrado; (2) credenciales incorrectas; (3) selectores desactualizados. "
                    f"Ver logs [galicia-diag] y [galicia-kbd] para diagnóstico."
                )
            raise RuntimeError(f"[galicia] Timeout esperando /inicio. URL: {cur[:200]}")

        cur = driver.current_url or ""
        logger.info("[galicia] Login OK — URL: %s", cur[:100])
        time.sleep(2)

        # ── Paso 7: navegar a Tarjetas (si no llegamos directo) ───────────────
        if "tarjetas.bancogalicia.com.ar" not in cur:
            logger.info("[galicia] Paso 7 — navegando a Tarjetas desde dashboard")
            self._navigate_to_tarjetas(driver)
        else:
            logger.info("[galicia] Ya en tarjetas domain — salteando paso 7")

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[galicia] %s", msg)
            log.append(msg)

        cur = driver.current_url or ""
        _log(f"URL al iniciar scrape: {cur[:120]}")

        # ── Estrategia de captura BFF ─────────────────────────────────────────
        # La SPA llama al BFF durante la navegación SSO en do_login().
        # El interceptor ya capturó esas respuestas en window.__galiciaBff.
        # Solo recargamos si todavía no hay datos (p.ej. check_session vacía el buffer).

        # Paso 1: intentar leer lo que ya existe (máx. 5s extra por si sigue cargando)
        _log("Verificando si BFF ya fue capturado por la SPA…")
        captured = self._wait_for_bff_capture(
            driver, ["overview/cards"], timeout_secs=5,
        )

        if not captured.get("overview/cards"):
            # Paso 2: no hay datos — navegar/recargar y esperar la SPA
            _log("Sin datos previos — navegando a /tarjetas/ini para activar SPA")
            self._reset_bff_capture(driver)
            if "/tarjetas/ini" not in cur:
                driver.get(_TARJETAS_URL)
            else:
                # Volvemos al dashboard y re-hacemos la navegación por SSO para que
                # la SPA cargue con contexto de autenticación completo
                _log("Intentando re-navegar via dashboard → Tarjetas")
                driver.get(_INICIO_URL)
                time.sleep(3)
                try:
                    self._navigate_to_tarjetas(driver)
                except Exception as nav_exc:
                    _log(f"Re-navegación fallida ({nav_exc}) — recargando directamente")
                    driver.get(_TARJETAS_URL)

            _log("Esperando que la SPA llame al BFF (hasta 25s)…")
            captured = self._wait_for_bff_capture(
                driver, ["overview/cards", "movements-tc"], timeout_secs=25,
            )

        ov_json = captured.get("overview/cards")
        mv_json = captured.get("movements-tc")
        _log(f"BFF capturado: overview={'sí' if ov_json else 'NO'}, movements={'sí' if mv_json else 'no'}")

        if not ov_json:
            cur2 = driver.current_url or ""
            # Log de claves presentes para diagnóstico
            raw = driver.execute_script(
                "return window.__galiciaBff ? JSON.stringify(Object.keys(window.__galiciaBff)) : '[]'"
            )
            _log(f"Claves en __galiciaBff: {raw}")
            raise RuntimeError(
                f"[galicia] BFF overview no capturado. URL: {cur2[:150]}. "
                f"Claves: {raw}. "
                f"Posible causa: la SPA no hizo llamadas fetch/XHR al BFF en esta sesión."
            )

        ov_data = (ov_json or {}).get("data", [])

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # Determinar fuente target (multi-instancia)
        fuente_target = self._fuente_for_product(config, "main", "galicia_mc")

        # Procesar cada grupo de tarjetas
        for grupo in ov_data:
            credit_cards = grupo.get("credit_cards") or []
            for card in credit_cards:
                movs, saldo = self._scrape_card(driver, card, mv_json, fuente_target, _log)
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
        mv_json: dict | None,
        fuente_target: str,
        log_fn,
    ) -> tuple[list[MovimientoRaw], float | None]:
        """
        Procesa una tarjeta de crédito usando los datos ya capturados por el interceptor.

        `card`    — objeto de la respuesta overview/cards
        `mv_json` — respuesta completa de movements-tc (capturada por el interceptor),
                    o None si la SPA no la llamó todavía
        """
        account_number = card.get("account_number") or ""
        last_four      = card.get("last_digits") or ""
        brand          = (card.get("brand") or "MASTER").upper()
        product        = card.get("product") or ""

        log_fn(f"Tarjeta: {brand} *{last_four} — cuenta {account_number} ({product})")

        # ── Período: detectar reset ───────────────────────────────────────────
        closing = card.get("settlement_closing_dates") or {}
        current_close = closing.get("current") or ""
        next_close    = closing.get("next")    or ""
        log_fn(f"Período: current={current_close}, next={next_close}")

        if current_close:
            stored_state = _read_period_state()
            stored_close = stored_state.get(fuente_target)
            if stored_close and stored_close != current_close:
                log_fn(
                    f"[PERÍODO RESET] Cierre cambió: {stored_close} → {current_close}. "
                    f"Borrando movimientos_raw de {fuente_target}…"
                )
                self._delete_movimientos_raw(fuente_target, log_fn)
            _write_period_state(fuente_target, current_close)

        # ── Consumo total (saldo) ─────────────────────────────────────────────
        saldo = None
        for c in card.get("consumption") or []:
            if (c.get("currency") or "").upper() == "ARS":
                saldo = float(c.get("total_amount") or 0)
                break

        # ── Obtener movimientos ───────────────────────────────────────────────
        # La SPA solo llama movements-tc en respuesta a interacción del usuario.
        # Si no fue capturado por el interceptor, llamamos al BFF directamente
        # ahora que la SPA ya cargó y la sesión está activa.
        if not mv_json:
            log_fn("movements-tc no en interceptor — llamando BFF directamente")
            brand_short = "MASTER" if brand.startswith("MASTER") else brand[:4].upper()
            payload: dict = {
                "credit_account_number":       account_number,
                "brand":                        brand_short,
                "card_number_last_four_digits": last_four,
                "is_additional":                False,
                "type":                         "open",
                "movement_type":                ["CONSUMPTION", "ADJUSTMENT", "PAYMENT", "AUTHORIZATION"],
            }
            if current_close and next_close:
                payload["date_from"] = current_close
                payload["date_to"]   = next_close

            mv_resp = self._bff_request(driver, "POST", _BFF_MOVEMENTS, payload)
            log_fn(f"BFF movements directo HTTP {mv_resp['status']}")
            if mv_resp["status"] == 200:
                mv_json = mv_resp["json"]
            else:
                log_fn(f"BFF movements error: {mv_resp['body'][:300]}")

        if not mv_json:
            log_fn("Sin movimientos disponibles")
            return [], saldo

        mv_data = (mv_json or {}).get("data", [])
        if not mv_data:
            log_fn("movements-tc: data vacía")
            return [], saldo

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

    def _dump_form_structure(self, driver) -> None:
        """
        Loguea todos los inputs, botones y formularios de la página actual.
        Imprescindible para calibrar selectores de login.
        """
        from selenium.webdriver.common.by import By
        try:
            logger.info("[galicia-diag] === ESTRUCTURA DE LA PÁGINA ===")
            logger.info("[galicia-diag] URL: %s", driver.current_url or "?")
            logger.info("[galicia-diag] Título: %r", driver.title or "?")

            # Forms
            forms = driver.find_elements(By.CSS_SELECTOR, "form")
            logger.info("[galicia-diag] Forms: %d", len(forms))
            for i, f in enumerate(forms):
                logger.info(
                    "[galicia-diag]   form[%d] id=%r action=%r",
                    i,
                    f.get_attribute("id") or "",
                    (f.get_attribute("action") or "")[:80],
                )

            # Inputs
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            logger.info("[galicia-diag] Inputs: %d", len(inputs))
            for inp in inputs[:20]:
                logger.info(
                    "[galicia-diag]   <input id=%r name=%r type=%r placeholder=%r class=%r>",
                    inp.get_attribute("id") or "",
                    inp.get_attribute("name") or "",
                    inp.get_attribute("type") or "",
                    (inp.get_attribute("placeholder") or "")[:40],
                    (inp.get_attribute("class") or "")[:50],
                )

            # Buttons
            btns = driver.find_elements(By.CSS_SELECTOR, "button")
            logger.info("[galicia-diag] Buttons: %d", len(btns))
            for b in btns[:12]:
                logger.info(
                    "[galicia-diag]   <button type=%r class=%r text=%r>",
                    b.get_attribute("type") or "",
                    (b.get_attribute("class") or "")[:60],
                    (b.text or "")[:40],
                )

        except Exception as exc:
            logger.info("[galicia-diag] error en dump_form: %s", exc)

    def _dump_keyboard_structure(self, driver) -> None:
        """
        Loguea la estructura del teclado virtual simple-keyboard si está presente.
        Muestra todos los contenedores de teclado y los valores data-skbtn disponibles.
        """
        from selenium.webdriver.common.by import By
        try:
            # Contenedores de teclado conocidos
            for sel in [".simple-keyboard", ".keyboard-container", "[class*='keyboard']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    logger.info("[galicia-kbd] Contenedor %r: %d elementos", sel, len(els))

            # Botones del teclado
            btns = driver.find_elements(By.CSS_SELECTOR, ".hg-button")
            logger.info("[galicia-kbd] .hg-button encontrados: %d", len(btns))
            if btns:
                skbtns = []
                texts = []
                for b in btns[:30]:
                    sk = b.get_attribute("data-skbtn") or ""
                    tx = (b.text or "").strip()
                    if sk:
                        skbtns.append(repr(sk))
                    elif tx:
                        texts.append(repr(tx))
                if skbtns:
                    logger.info("[galicia-kbd] data-skbtn values: %s", ", ".join(skbtns))
                if texts:
                    logger.info("[galicia-kbd] button texts (sin data-skbtn): %s", ", ".join(texts))

            # Alternativa: buscar cualquier botón dentro del keyboard
            for sel in ["[class*='keyboard'] button", "[class*='key'] button",
                        ".key button", "button[data-key]", "button[data-char]"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    sample = [
                        f"text={repr((e.text or '').strip()[:4])} "
                        f"data-key={repr(e.get_attribute('data-key') or '')} "
                        f"data-char={repr(e.get_attribute('data-char') or '')}"
                        for e in els[:8]
                    ]
                    logger.info("[galicia-kbd] %r: %d btns → %s", sel, len(els), "; ".join(sample))

        except Exception as exc:
            logger.info("[galicia-kbd] error en dump_keyboard: %s", exc)

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

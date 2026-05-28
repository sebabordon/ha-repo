"""
Scraper BBVA Argentina — todas las requests API se hacen DESDE el browser real.

Estrategia (confirmada por análisis HAR + iteración):
  1. Selenium carga la página de login → Akamai Bot Manager inicializa cookies
     anti-bot en el browser real (no se puede replicar sin un browser verdadero).
  2. Todas las llamadas a la API se hacen vía `execute_async_script` con
     `fetch()` dentro de Chrome — Akamai valida fingerprint del cliente HTTP
     (TLS, headers, JA3, etc.) y rechaza httpx con 403 incluso teniendo las
     cookies correctas.  fetch() pasa porque corre en el mismo browser que
     generó las cookies.
  3. Login en dos pasos:
       POST /login/prelogin   → devuelve redirect URL con sessionIdLN
       POST /login/postlogin  → establece la sesión definitiva
  No se interactúa con el formulario HTML (web components Lit/Spherica que
  son extremadamente difíciles de automatizar en modo headless).

API base: https://online.bbva.com.ar/fnetcore/servicios/
Auth:     cookies de sesión de postlogin (jsessionid + otras), persistidas
          por _save_session().

Credenciales:
  usuario     → número de DNI
  tercer_dato → nombre de usuario BBVA (el alias configurado en homebanking)
  password    → contraseña / clave digital

Endpoints:
  POST /login/prelogin                            → primer paso de auth; devuelve sessionId
  POST /login/postlogin                           → segundo paso; establece sesión
  GET  /cliente/datosperfil                       → verifica sesión; devuelve nombre
  GET  /cliente/productos/cuentas                 → lista de cuentas (cajasAhorro[])
  POST /cliente/productos/cuentas/movimientos     → movimientos paginados

Detección de signo (importe siempre positivo en la API):
  La respuesta viene newest-first.
  Si saldo[i] > saldo[i+1] → ingreso (sign = −1, monto < 0)
  Si saldo[i] < saldo[i+1] → egreso  (sign = +1, monto > 0)
  Último movimiento del batch (sin siguiente) → default egreso.
"""

import json as _json
import logging
import re
import secrets
import string
import time
from datetime import datetime, timedelta, timezone

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://online.bbva.com.ar/fnetcore/login/index.html"
_API_BASE  = "https://online.bbva.com.ar/fnetcore/servicios"

# Argentina — sin horario de verano
_ART = timezone(timedelta(hours=-3))

_DIAS_DEFAULT = 60
_PAGE_SIZE    = 10   # BBVA devuelve 10 movimientos por llamada (confirmado por HAR)

# versionFront: versión del bundle del login, enviada en el payload de prelogin.
# Valor confirmado por HAR del 2026-05-27.  Se intenta extraer del HTML en
# _extract_version_front(); si falla se usa este fallback.
_VERSION_FRONT_FALLBACK = "20260325.1526"

def _ts() -> str:
    """Cache-buster en milisegundos, igual que el frontend de BBVA."""
    return str(int(time.time() * 1000))


_SESSION_ID_LN_ALPHABET = string.ascii_lowercase + string.digits

def _make_session_id_ln() -> str:
    """Genera sessionIdLN de 128 chars [a-z0-9], igual al que produce el JS de loginClementeApp2."""
    return ''.join(secrets.choice(_SESSION_ID_LN_ALPHABET) for _ in range(128))


class BbvaScraper(BaseScraper):
    fuente       = "bbva"
    nombre       = "BBVA Argentina"
    login_origin = "https://online.bbva.com.ar"

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _driver_cookies(self, driver) -> dict[str, str]:
        """Extrae las cookies del WebDriver (útil para _save_session y diagnóstico)."""
        return {c["name"]: c["value"] for c in driver.get_cookies()}

    def _fetch_url(self, driver, url: str, timeout: int = 30) -> dict:
        """
        Hace un GET fetch() a una URL arbitraria dentro del browser (sin navegar).
        Útil para que el browser aplique las cookies Set-Cookie de la respuesta
        sin arriesgar un crash del renderer por navegación de página.
        Returns dict {status: int, body: str}.
        """
        js = """
        var url = arguments[0];
        var cb  = arguments[arguments.length - 1];
        fetch(url, {method: 'GET', credentials: 'include'})
            .then(function(r) { return r.text().then(function(t) { cb({status: r.status, body: t}); }); })
            .catch(function(e) { cb({status: 0, body: 'fetch_url error: ' + String(e)}); });
        """
        try:
            driver.set_script_timeout(timeout + 5)
        except Exception:
            pass
        try:
            result = driver.execute_async_script(js, url)
        except Exception as exc:
            logger.warning("[bbva] _fetch_url error: %s", exc)
            return {"status": 0, "body": str(exc)}
        if not isinstance(result, dict):
            return {"status": 0, "body": f"invalid result: {result!r}"}
        return {"status": int(result.get("status", 0) or 0), "body": str(result.get("body", "") or "")}

    def _api_request(
        self,
        driver,
        path: str,
        method: str = "GET",
        json_body: dict | None = None,
        timeout: int = 30,
        with_xsrf: bool = True,
    ) -> dict:
        """
        Hace una request a la API REST de BBVA desde DENTRO del browser real
        (via fetch + execute_async_script), NO desde httpx.

        Motivo: Akamai Bot Manager hace fingerprinting del cliente HTTP (TLS,
        headers, JA3, etc.) y rechaza httpx con HTTP 403 incluso teniendo las
        cookies correctas.  fetch() corre dentro de Chrome y por lo tanto tiene
        el fingerprint válido que generó las cookies de Akamai en primer lugar.

        Returns: dict con {"status": int, "body": str, "json": dict|None}
        """
        url = f"{_API_BASE}{path}?ts={_ts()}"
        body_str = _json.dumps(json_body) if json_body is not None else None

        js = """
        var url      = arguments[0];
        var method   = arguments[1];
        var body     = arguments[2];
        var withXsrf = arguments[3];
        var cb       = arguments[arguments.length - 1];

        var opts = {
            method: method,
            headers: {
                'Accept':          'application/json, text/plain, */*',
                'Accept-Language': 'es-AR,es;q=0.9'
            },
            credentials: 'include'
        };
        if (body !== null) {
            opts.headers['Content-Type'] = 'application/json;charset=UTF-8';
            opts.body = body;
        }

        // Angular $http lee la cookie XSRF-TOKEN y la reenvía como X-XSRF-TOKEN.
        // Solo lo incluimos en llamadas autenticadas (post-login); prelogin y
        // postlogin no deben incluirlo porque el token de sesión aún no es válido.
        if (withXsrf) {
            var xsrf = null;
            try {
                document.cookie.split(';').forEach(function(c) {
                    var p = c.trim();
                    if (p.startsWith('XSRF-TOKEN=')) xsrf = decodeURIComponent(p.substring(11));
                });
            } catch(e) {}
            if (xsrf) opts.headers['X-XSRF-TOKEN'] = xsrf;
        }

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
            result = driver.execute_async_script(js, url, method, body_str, with_xsrf)
        except Exception as exc:
            logger.warning("[bbva] _api_request execute_async_script error: %s", exc)
            return {"status": 0, "body": f"execute_async_script error: {exc}", "json": None}

        if not isinstance(result, dict):
            return {"status": 0, "body": f"invalid result: {result!r}", "json": None}

        status = int(result.get("status", 0) or 0)
        body   = str(result.get("body", "") or "")
        parsed = None
        try:
            parsed = _json.loads(body) if body else None
        except Exception:
            parsed = None

        return {"status": status, "body": body, "json": parsed}

    def _extract_version_front(self, driver) -> str:
        """
        Extrae versionFront del HTML de la página de login.
        Formato: 8 dígitos + punto + dígitos (ej: "20260325.1526").
        Si no se encuentra, devuelve _VERSION_FRONT_FALLBACK.
        """
        try:
            source = driver.page_source
            # Buscar en JSON embebido: "versionFront":"XXXXXXXX.XXXX"
            m = re.search(r'"versionFront"\s*:\s*"(\d{8}\.\d+)"', source)
            if m:
                return m.group(1)
            # Buscar en parámetros ts= de URLs de assets (misma versión usada como versionFront)
            m = re.search(r'\bts=(\d{8}\.\d+)\b', source)
            if m:
                return m.group(1)
        except Exception as exc:
            logger.info("[bbva] _extract_version_front error: %s", exc)
        return _VERSION_FRONT_FALLBACK

    def _type_input(self, driver, element, value: str) -> None:
        """
        Escribe en un campo de formulario con estrategias progresivas.

        Problema: BBVA usa @bbva/webcomponents (Lit + elementos Shadow DOM);
        los <input> nativos dentro del web component pueden no ser interactuables
        con send_keys() directo en modo headless.

        Estrategia 1 — ActionChains (la más "humana"):
          scroll al elemento → move_to_element → click → send_keys

        Estrategia 2 — JS nativo (para React / Lit / Angular):
          Usa el setter del prototipo de HTMLInputElement para bypassear el
          framework, luego dispara eventos 'input' y 'change' con bubbles=true
          para que el framework detecte el cambio.

        Estrategia 3 — última reserva:
          execute_script("arguments[0].value = arguments[1]", el, value)
          + disparo manual de eventos (sin prototipo).
        """
        from selenium.webdriver.common.action_chains import ActionChains

        # ── Estrategia 1: ActionChains encadenado (click + send_keys en una sola acción) ──
        # send_keys() en ActionChains manda keystrokes al elemento ACTUALMENTE ENFOCADO
        # en el browser, no al WebElement directamente.  Para Lit/Shadow DOM esto es
        # la diferencia clave: element.send_keys() falla porque el WebElement no es
        # "interactable", pero ActionChains.click(el).send_keys(val) enfoca primero y
        # luego escribe via eventos de teclado reales.
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.3)
            ActionChains(driver).click(element).send_keys(value).perform()
            return
        except Exception as e1:
            logger.info("[bbva] _type_input estrategia 1 falló (%s), probando JS", e1)

        # ── Estrategia 2: JS con setter nativo + eventos React/Lit ───────────
        try:
            driver.execute_script(
                """
                var el  = arguments[0];
                var val = arguments[1];
                try {
                    var setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(el, val);
                } catch(e) {
                    el.value = val;
                }
                ['input', 'change', 'blur'].forEach(function(t) {
                    el.dispatchEvent(new Event(t, {bubbles: true, cancelable: true}));
                });
                """,
                element, value,
            )
            return
        except Exception as e2:
            logger.info("[bbva] _type_input estrategia 2 falló (%s), probando fallback", e2)

        # ── Estrategia 3: assign directo (fallback final) ─────────────────────
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input',  {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            element, value,
        )

    def _click_element(self, driver, element) -> None:
        """
        Hace clic en un elemento con fallback a JS.

        Mismo problema que _type_input: botones dentro de web components
        Lit/Spherica no son interactuables con .click() directo en headless.

        Estrategia 1 — ActionChains scroll + click (más confiable en headless).
        Estrategia 2 — JS element.click() (bypasea la capa de interactabilidad).
        """
        from selenium.webdriver.common.action_chains import ActionChains

        # Estrategia 1: ActionChains
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.2)
            ActionChains(driver).move_to_element(element).click().perform()
            return
        except Exception as e1:
            logger.info("[bbva] _click_element estrategia 1 falló (%s), probando JS", e1)

        # Estrategia 2: JS click
        driver.execute_script("arguments[0].click();", element)

    def _dump_page_state(self, driver) -> None:
        """
        Emite al log (INFO) información diagnóstica de la página actual.
        Útil para calibrar selectores cuando el login falla.
        """
        try:
            logger.info("[bbva-diag] Título: %r", driver.title)
            logger.info("[bbva-diag] URL: %s", driver.current_url)

            inputs = driver.find_elements("css selector", "input")
            logger.info("[bbva-diag] inputs en frame actual: %d", len(inputs))
            for inp in inputs[:8]:
                logger.info(
                    "[bbva-diag]   <input id=%r type=%r name=%r placeholder=%r>",
                    inp.get_attribute("id") or "",
                    inp.get_attribute("type") or "",
                    inp.get_attribute("name") or "",
                    (inp.get_attribute("placeholder") or "")[:40],
                )

            iframes = driver.find_elements("css selector", "iframe")
            logger.info("[bbva-diag] iframes encontrados: %d", len(iframes))
            for idx, fr in enumerate(iframes[:6]):
                src = (fr.get_attribute("src") or "")[:80]
                fid = fr.get_attribute("id") or ""
                logger.info("[bbva-diag]   iframe[%d] id=%r src=%r", idx, fid, src)

            # Dump de los primeros 800 chars del body para ver la estructura
            try:
                body = driver.execute_script(
                    "return document.body ? document.body.innerHTML.slice(0,800) : '(sin body)'"
                )
                logger.info("[bbva-diag] body[:800]: %s", body)
            except Exception:
                pass

        except Exception as exc:
            logger.info("[bbva-diag] error en dump: %s", exc)

    # ── check_session ─────────────────────────────────────────────────────────

    def check_session(self, driver) -> bool:
        """
        Verifica si la sesión sigue activa llamando a datosperfil DESDE el browser.

        Requiere que _restore_session() ya haya navegado al login_origin (lo hace
        antes de inyectar cookies) — así fetch() corre con same-origin a la API.
        """
        # Si el driver está en about:blank (sin navegación), primero cargar el dominio
        try:
            cur = driver.current_url or ""
            if "bbva.com.ar" not in cur:
                driver.get(_LOGIN_URL)
                time.sleep(3)
        except Exception:
            pass

        try:
            resp = self._api_request(driver, "/cliente/datosperfil")
            logger.info("[bbva] check_session HTTP %d", resp["status"])
            if resp["status"] == 200 and resp["json"]:
                return bool(resp["json"].get("result"))
        except Exception as exc:
            logger.info("[bbva] check_session error: %s", exc)
        return False

    # ── do_login ──────────────────────────────────────────────────────────────

    def do_login(self, driver, config: dict) -> None:
        """
        Login BBVA en dos pasos via API REST directa (NO interacción con formulario HTML).

        Estrategia confirmada por análisis HAR (2026-05-27):

          Paso 1 — Akamai:
            Selenium carga la página de login.  El JS de Akamai Bot Manager
            corre en el browser real y setea cookies anti-bot (_abck, bm_sz, etc.)
            que el servidor valida en cada request.  Sin estas cookies las llamadas
            API son rechazadas.

          Paso 2 — prelogin:
            POST /login/prelogin con { documento, usuario, claveDigital, versionFront }.
            Respuesta 200: JSON con redirect URL que codifica sessionIdLN y
            numeroClienteAltamira.

          Paso 3 — postlogin directo:
            Genera sessionIdLN aleatorio (128 chars [a-z0-9]).
            POST /login/postlogin con { numeroClienteAltamira, sessionIdLN }.
            Establece las cookies de sesión definitivas (jsessionid, etc.).
            No se navega a loginClementeApp2.html porque la URL con el token
            authentication crashea headless Chromium.

          Paso 4 — verificar:
            GET /cliente/datosperfil con las cookies combinadas.
        """
        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        # ── Paso 1: cargar página → Akamai inicializa cookies anti-bot ────────
        logger.info("[bbva] cargando login page para Akamai: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        # Esperar a que los scripts de Akamai Y Adobe Analytics terminen de ejecutar.
        # Sin cookies s_cc/s_visit (Adobe), Akamai bloquea prelogin con 403.
        # Esperamos hasta 15 s en pasos de 1 s, o hasta que las cookies estén listas.
        for _w in range(15):
            time.sleep(1)
            _ck = {c["name"] for c in driver.get_cookies()}
            if "_abck" in _ck and "s_visit" in _ck:
                logger.info("[bbva] Akamai+Adobe cookies listas tras %ds", _w + 1)
                break
        else:
            logger.info("[bbva] timeout esperando cookies Akamai (continuando igual)")
        self._dump_page_state(driver)

        version_front  = self._extract_version_front(driver)
        cookies_akamai = self._driver_cookies(driver)
        _abck_len = len(cookies_akamai.get("_abck", ""))
        logger.info(
            "[bbva] Akamai cookies (%d): %s  |  versionFront: %s  |  _abck len=%d",
            len(cookies_akamai), sorted(cookies_akamai.keys()), version_front, _abck_len,
        )

        # ── Paso 2: POST prelogin (vía fetch del browser, NO httpx) ───────────
        # Akamai hace fingerprinting del cliente HTTP y rechaza httpx con 403.
        # fetch() dentro de Chrome pasa la validación porque es el mismo browser
        # que generó las cookies _abck/bm_sz.
        prelogin_payload = {
            "documento": {
                "numeroDocumento": dni,
                "genero": "",
                "tipoDocumento": {
                    "codigoTipoDocumento": "0",
                    "descripcionCorta": "DNI",
                    "descripcion": "DNI",
                },
            },
            "usuario":      username,
            "claveDigital": password,
            "versionFront": version_front,
            "rememberData": False,
        }

        pre = self._api_request(
            driver, "/login/prelogin", method="POST", json_body=prelogin_payload,
            with_xsrf=False,
        )
        logger.info("[bbva] prelogin HTTP %d  body=%s", pre["status"], pre["body"][:500])

        if pre["status"] != 200:
            raise RuntimeError(
                f"[bbva] prelogin HTTP {pre['status']}: {pre['body'][:300]}"
            )

        # ── Paso 3: validar loginOk y extraer authentication + numeroCliente ──
        # La response real de prelogin (confirmada en producción) trae:
        #   { loginOk, authentication, numeroClienteAltamira, codigoTipoIngreso, ... }
        # El sessionIdLN del postlogin lo genera el frontend al navegar a
        # loginClementeApp2.html (NO viene del servidor), así que dejamos al
        # browser hacer ese paso por nosotros.
        pre_result = ((pre["json"] or {}).get("result") or {})

        if not pre_result.get("loginOk"):
            raise RuntimeError(
                f"[bbva] prelogin loginOk=false. Posibles credenciales inválidas. "
                f"Body: {pre['body'][:300]}"
            )

        authentication = str(pre_result.get("authentication", "") or "")
        numero_cliente = str(pre_result.get("numeroClienteAltamira", "") or "")

        if not authentication or not numero_cliente:
            raise RuntimeError(
                f"[bbva] prelogin OK pero faltan datos (authentication o numeroClienteAltamira). "
                f"Campos en result: {list(pre_result.keys())}"
            )

        logger.info(
            "[bbva] authentication len=%d  numeroCliente=%s  marcaTipoUsuario=%s",
            len(authentication), numero_cliente,
            pre_result.get("marcaTipoUsuario", "?"),
        )

        # ── Paso 4: navegar a loginClementeApp2.html (sin query string) ─────────
        # Akamai BotManager ejecuta sus scripts de sensor en cada navegación
        # de página y actualiza el cookie `_abck`.  Postlogin se llama
        # normalmente DESDE loginClementeApp2.html; si lo llamamos desde
        # login/index.html (mismo contexto que prelogin), el `_abck` no fue
        # actualizado y el servidor responde con statusCode:500.
        #
        # Solución: navegar a loginClementeApp2.html SIN query string (URL corta,
        # sin token de authentication → no crashea headless Chrome), esperar a
        # que Akamai actualice _abck, y luego llamar postlogin desde ese contexto.
        # ── Paso 4a: navegar a loginClementeApp2.html para actualizar Akamai ────
        # Akamai BotManager re-ejecuta sus scripts de sensor en cada navegación.
        # Postlogin debe venir de ese contexto de página (Akamai `_abck` fresco
        # + Referer correcto).  También el servidor BBVA puede requerir el GET a
        # loginClementeApp2.html para registrar internamente la sesión previa al
        # postlogin.
        #
        # Preferimos la URL COMPLETA (con el token de authentication) para que
        # el servidor pueda validar la sesión; usamos window.location.href = url
        # (en lugar de driver.get) porque es más resistente a crash del renderer.
        # Fallback: URL base (sin token) si la navegación JS falla.
        session_id_ln = _make_session_id_ln()
        clemente_url_full = (
            f"https://online.bbva.com.ar/fnetcore/loginClementeApp2.html"
            f"?{authentication}=/std/{numero_cliente}/0/{dni}//{session_id_ln}"
        )
        clemente_url_base = "https://online.bbva.com.ar/fnetcore/loginClementeApp2.html"

        # Intentar navegación JS con URL completa (el token de authentication
        # no tiene slashes reales — usa ==SLASH== — por lo que driver.get falla
        # pero window.location.href puede manejarlo mejor)
        logger.info("[bbva] navegando a loginClementeApp2 vía JS (url len=%d)", len(clemente_url_full))
        try:
            driver.execute_script("window.location.href = arguments[0];", clemente_url_full)
            _nav_ok = True
        except Exception as _nav_err:
            logger.info("[bbva] JS nav completo falló (%s), usando URL base", _nav_err)
            driver.get(clemente_url_base)
            _nav_ok = False

        # Esperar a que Akamai actualice _abck (hasta 12 s)
        for _w in range(12):
            time.sleep(1)
            _ck2 = {c["name"]: c["value"] for c in driver.get_cookies()}
            if "_abck" in _ck2 and len(_ck2.get("_abck", "")) > 100:
                logger.info("[bbva] loginClementeApp2 Akamai OK (abck len=%d, full=%s) tras %ds",
                            len(_ck2["_abck"]), _nav_ok, _w + 1)
                break
        else:
            logger.info("[bbva] loginClementeApp2: timeout esperando _abck (continuando)")
        postlogin_payload = {
            "documento": {
                "tipoDocumento": {
                    "codigoTipoDocumento": "0",
                    "descripcionCorta": "",
                    "descripcion": "",
                },
                "numeroDocumento": dni,
                "genero": "",
            },
            "usuario":               "",
            "claveDigital":          "",
            "numeroClienteAltamira": numero_cliente,
            "sessionIdLN":           session_id_ln,
        }
        logger.info("[bbva] postlogin (sessionIdLN[:16]=%s…)", session_id_ln[:16])
        post = self._api_request(
            driver, "/login/postlogin", method="POST", json_body=postlogin_payload,
            with_xsrf=False,
        )
        logger.info("[bbva] postlogin HTTP %d  body[:200]=%s", post["status"], post["body"][:200])
        if post["status"] != 200:
            raise RuntimeError(
                f"[bbva] postlogin HTTP {post['status']}: {post['body'][:300]}"
            )
        # Verificar statusCode en el body (BBVA usa HTTP 200 incluso para errores de aplicación)
        post_result = (post["json"] or {})
        if str(post_result.get("statusCode", "200")) != "200":
            raise RuntimeError(
                f"[bbva] postlogin error: {post_result.get('statusText', '')} "
                f"(statusCode={post_result.get('statusCode')})"
            )

        # ── Paso 4b: obtenerTsec — establece cookie XSRF-TOKEN ────────────────
        # Angular $http lee XSRF-TOKEN y lo reenvía como X-XSRF-TOKEN en cada
        # request. Sin este paso la cookie no existe y datosperfil (y todo lo
        # demás) devuelve 403 "Invalid CSRF Token 'null'".
        tsec = self._api_request(driver, "/seguridad/cliente/obtenerTsec")
        logger.info("[bbva] obtenerTsec HTTP %d  body=%s", tsec["status"], tsec["body"][:100])

        # ── Paso 5: verificar sesión con datosperfil ──────────────────────────
        perf = self._api_request(driver, "/cliente/datosperfil")
        logger.info("[bbva] datosperfil HTTP %d  body[:200]=%s", perf["status"], perf["body"][:200])

        if perf["status"] == 200 and perf["json"]:
            perfil = ((perf["json"].get("result") or {}).get("perfilCliente", {}))
            nombre = perfil.get("nombre", "?")
            logger.info("[bbva] Login OK — usuario: %s", nombre)
            return

        raise RuntimeError(
            f"[bbva] datosperfil HTTP {perf['status']} tras postlogin. "
            f"datosperfil body: {perf['body'][:300]}"
        )

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva] %s", msg)
            log.append(msg)

        dias = int(config.get("dias") or _DIAS_DEFAULT)

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # ── Obtener lista de cuentas (via fetch del browser) ──────────────────
        cuentas_resp = self._api_request(driver, "/cliente/productos/cuentas")
        if cuentas_resp["status"] != 200:
            raise RuntimeError(
                f"[bbva] cuentas HTTP {cuentas_resp['status']}: {cuentas_resp['body'][:200]}"
            )

        result = (cuentas_resp["json"] or {}).get("result", {}) or {}
        cajas  = result.get("cajasAhorro", []) or []
        _log(f"Cuentas encontradas: {len(cajas)}")

        today_art   = datetime.now(_ART).date()
        since_date  = today_art - timedelta(days=dias - 1)
        fecha_desde = since_date.strftime("%d/%m/%Y")
        fecha_hasta = today_art.strftime("%d/%m/%Y")
        _log(f"Rango: {fecha_desde} → {fecha_hasta} ({dias} días)")

        for cuenta in cajas:
            id_prod   = cuenta.get("id", "")
            alias     = cuenta.get("alias", id_prod)
            saldo_raw = cuenta.get("saldo") or cuenta.get("importe") or ""

            _log(f"Procesando cuenta: {alias} (id={id_prod})")

            if saldo_raw:
                saldo_val = self.parse_amount(str(saldo_raw))
                saldos["bbva_cuenta"] = {"saldo_ars": saldo_val}
                _log(f"  Saldo actual: {saldo_raw}")

            movs = self._fetch_movimientos(
                driver, id_prod, fecha_desde, fecha_hasta, _log,
            )
            _log(f"  → {len(movs)} movimientos importados de {alias}")
            movimientos.extend(movs)

        return ScraperResult(
            fuente      = "bbva",
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    # ── paginación ─────────────────────────────────────────────────────────────

    def _fetch_movimientos(
        self,
        driver,
        id_producto: str,
        fecha_desde: str,
        fecha_hasta: str,
        log_fn,
    ) -> list[MovimientoRaw]:
        """
        Pagina la API de movimientos hasta obtenerlos todos (vía fetch del browser).

        Primera llamada: payload completo con fechaDesde/fechaHasta.
        Llamadas siguientes: sólo idProducto + ultimoMovimientoMostrado (int).
        La API devuelve ≤ 10 movimientos por página.
        """
        all_movs: list[MovimientoRaw] = []
        ultimo = 0

        while True:
            if ultimo == 0:
                payload: dict = {
                    "idProducto":               id_producto,
                    "ultimoMovimientoMostrado": "0",
                    "filtro":                   False,
                    "fechaDesde":               fecha_desde,
                    "fechaHasta":               fecha_hasta,
                    "importeDesde":             "",
                    "importeHasta":             "",
                    "codigoTipoMovimiento":     "",
                    "idRubroMovimiento":        "",
                }
            else:
                payload = {
                    "idProducto":               id_producto,
                    "ultimoMovimientoMostrado": ultimo,
                }

            resp = self._api_request(
                driver,
                "/cliente/productos/cuentas/movimientos",
                method="POST",
                json_body=payload,
            )
            if resp["status"] != 200:
                log_fn(
                    f"  movimientos HTTP {resp['status']} — deteniendo paginación. "
                    f"body: {resp['body'][:200]}"
                )
                break

            data  = (resp["json"] or {}).get("result", {}) or {}
            count = data.get("count", 0)
            batch = data.get("movimientos", []) or []

            if not batch:
                break

            log_fn(f"  Página desde={ultimo}: {len(batch)} movimientos (API total={count})")
            all_movs.extend(self._parse_batch(batch))

            # Si devolvió menos de _PAGE_SIZE, no hay más páginas
            if len(batch) < _PAGE_SIZE:
                break

            ultimo += len(batch)

        return all_movs

    # ── parsing de un batch ───────────────────────────────────────────────────

    def _parse_batch(self, batch: list[dict]) -> list[MovimientoRaw]:
        """
        Convierte un batch de movimientos BBVA a MovimientoRaw.

        El array llega newest-first.  El signo se deduce comparando saldos:
          saldo[i]  >  saldo[i+1]  →  ingreso (sign = −1)
          saldo[i]  <  saldo[i+1]  →  egreso  (sign = +1)
          saldo[i] ==  saldo[i+1]  →  egreso  (default)
          último elemento (sin siguiente)  →  egreso  (default)

        monto se guarda con el signo de la convención del proyecto:
          monto > 0 = egreso   (plata que sale)
          monto < 0 = ingreso  (plata que entra)
        """
        result: list[MovimientoRaw] = []

        for i, mov in enumerate(batch):
            fecha = self.parse_date_ar(mov.get("fecha", ""))
            if not fecha:
                continue

            importe_str = str(mov.get("importe", "0") or "0")
            saldo_str   = str(mov.get("saldo",   "0") or "0")
            importe_abs = abs(self.parse_amount(importe_str))
            saldo_val   = self.parse_amount(saldo_str)

            # Signo por diferencia de saldos (newest-first)
            if i + 1 < len(batch):
                saldo_prev = self.parse_amount(
                    str(batch[i + 1].get("saldo", "0") or "0")
                )
                if saldo_val > saldo_prev:
                    sign = -1   # saldo subió → ingreso
                elif saldo_val < saldo_prev:
                    sign = +1   # saldo bajó  → egreso
                else:
                    sign = +1   # sin cambio   → default egreso
            else:
                sign = +1       # sin referencia → default egreso

            monto = importe_abs * sign

            concepto = (mov.get("concepto") or "").strip()
            canal    = (mov.get("canal")    or "").strip()
            desc     = concepto or canal or "Movimiento BBVA"

            raw_data = {
                "saldo":                  saldo_str,
                "canal":                  canal or None,
                "numero_operacion":       mov.get("numeroOperacion") or None,
                "referencia":             mov.get("referencia")      or None,
                "clave_concepto":         mov.get("claveConcepto")   or None,
                "codigo_tipo_movimiento": mov.get("codigoTipoMovimiento") or None,
                "tiene_detalle":          mov.get("tieneDetalle"),
            }
            # Limpiar None para no inflar el raw_data
            raw_data = {k: v for k, v in raw_data.items() if v is not None}

            result.append(MovimientoRaw(
                fuente      = "bbva_cuenta",
                fecha       = fecha,
                descripcion = desc,
                monto       = monto,
                moneda      = "ARS",
                raw_data    = raw_data,
            ))

        return result

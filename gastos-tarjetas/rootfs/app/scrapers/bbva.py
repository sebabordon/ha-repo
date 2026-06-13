"""
Scraper BBVA Argentina — login NATURAL en browser + scraping vía API.

Estrategia:
  1. LOGIN — interacción real con el formulario HTML:
     - Selenium carga `login/index.html`
     - Esperamos a que Akamai BotManager y Adobe Analytics seteen sus cookies
     - Llenamos los 3 inputs (DNI, alias, password) con ActionChains (necesario
       para los web components Lit/Spherica que envuelven los `<input>` nativos)
     - Click en submit
     - Esperamos a que el browser navegue fuera de `/login/` (BBVA hace todo
       el flujo prelogin → loginClementeApp2.html → postlogin → fnetcore/
       automáticamente, incluyendo Akamai sensor refresh, sessionIdLN, XSRF, etc.)
     - Verificamos con `datosperfil` que la sesión esté activa.
  2. SCRAPE — una vez logueados, todas las llamadas REST se hacen desde
     dentro del browser vía `execute_async_script` + `fetch()`.  Akamai
     acepta esas requests porque corren en el mismo browser que generó la
     sesión.

API base: https://online.bbva.com.ar/fnetcore/servicios/
Auth:     cookies de sesión establecidas por el login natural, persistidas
          por _save_session() para skipear el login en runs siguientes.

Credenciales:
  usuario     → número de DNI
  tercer_dato → nombre de usuario BBVA (el alias configurado en homebanking)
  password    → contraseña / clave digital

Endpoints (post-login):
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
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

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


class BbvaScraper(BaseScraper):
    fuente        = "bbva"
    nombre        = "BBVA Argentina"
    login_origin  = "https://online.bbva.com.ar"
    # BBVA cierra la sesión por inactividad a los 5 minutos.  Como los runs
    # ocurren con al menos 30 min de separación, cualquier sesión guardada ya
    # estará vencida.  No guardar las cookies evita el ciclo de cookies stale
    # → redirect a /desconexion.html que forzaba un segundo login.
    save_session  = False

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _driver_cookies(self, driver) -> dict[str, str]:
        """Extrae las cookies del WebDriver (útil para _save_session y diagnóstico)."""
        return {c["name"]: c["value"] for c in driver.get_cookies()}

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
        Login BBVA via interacción NATURAL con el formulario (no API directa).

        Estrategia: dejamos que el browser real haga TODO el flujo de login —
        Akamai, prelogin, navegación a loginClementeApp2.html, generación de
        sessionIdLN, postlogin, obtenerTsec, etc.  Nosotros sólo:
          1. Cargamos la página de login.
          2. Esperamos a que Akamai/Adobe completen sus scripts (cookies presentes).
          3. Llenamos los 3 inputs (DNI, usuario, password) usando ActionChains
             (necesario para Lit/Shadow DOM web components).
          4. Hacemos click en el botón submit.
          5. Esperamos a que la URL deje de ser /login/index.html (el browser
             navega a loginClementeApp2.html → /fnetcore/).
          6. Verificamos con datosperfil que la sesión esté activa.

        Esto evita por completo los problemas de bypass de Akamai (que rechazaba
        nuestras llamadas API hechas con fetch desde un contexto incorrecto),
        las complicaciones de XSRF-TOKEN, la generación de sessionIdLN y
        cualquier crash del renderer por URLs largas con ==SLASH==.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        # ── Paso 0: limpiar cookies stale ─────────────────────────────────────
        # Si venimos de un check_session que falló, hay cookies expiradas en el
        # browser.  Si las dejamos, al cargar /login/index.html BBVA detecta la
        # sesión vencida y redirige a /desconexion.html en lugar de mostrar el
        # formulario → submit termina en desconexion y el login falla.
        # delete_all_cookies() borra sólo las del dominio actual; si el driver
        # está en about:blank navegamos primero a la raíz BBVA.
        try:
            cur = driver.current_url or ""
            if "bbva.com.ar" not in cur:
                driver.get("https://online.bbva.com.ar/")
                time.sleep(1)
            driver.delete_all_cookies()
            logger.info("[bbva] cookies stale eliminadas antes del login")
        except Exception as _ck_exc:
            logger.info("[bbva] no se pudieron eliminar cookies stale: %s", _ck_exc)

        # ── Paso 1: cargar página y esperar Akamai+Adobe ──────────────────────
        logger.info("[bbva] cargando login page: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        for _w in range(15):
            time.sleep(1)
            _ck = {c["name"] for c in driver.get_cookies()}
            if "_abck" in _ck and "s_visit" in _ck:
                logger.info("[bbva] Akamai+Adobe cookies listas tras %ds", _w + 1)
                break
        else:
            logger.info("[bbva] timeout esperando cookies Akamai (continuando)")

        # ── Paso 2: localizar los 3 inputs del formulario ─────────────────────
        # Selectores observados (estables — sin depender de los IDs auto-generados):
        #   <input type='number' …>                  → DNI
        #   <input type='password' name='username' …> → alias homebanking
        #   <input type='password' name='password' …> → clave digital
        try:
            dni_input  = WebDriverWait(driver, 15).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "input[type='number']")
            )
        except Exception as exc:
            self._dump_page_state(driver)
            raise RuntimeError(f"[bbva] no se encontró el input de DNI: {exc}")

        try:
            user_input = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            pass_input = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        except Exception as exc:
            self._dump_page_state(driver)
            raise RuntimeError(f"[bbva] no se encontraron inputs usuario/password: {exc}")

        logger.info("[bbva] inputs encontrados — llenando formulario")

        # ── Paso 3: llenar inputs (usar _type_input por Lit/Shadow DOM) ───────
        self._type_input(driver, dni_input,  dni)
        self._type_input(driver, user_input, username)
        self._type_input(driver, pass_input, password)

        # ── Paso 4: localizar y clickear el botón submit ──────────────────────
        submit_el = None
        for sel in [
            "form#login button[type='submit']",
            "button[type='submit']",
            "form button:last-of-type",
        ]:
            try:
                submit_el = driver.find_element(By.CSS_SELECTOR, sel)
                if submit_el:
                    logger.info("[bbva] botón submit encontrado: %s", sel)
                    break
            except Exception:
                continue

        if submit_el is None:
            self._dump_page_state(driver)
            raise RuntimeError("[bbva] no se encontró el botón submit del formulario")

        self._click_element(driver, submit_el)
        logger.info("[bbva] submit clickeado — esperando navegación a /fnetcore/")

        # ── Paso 5: esperar a llegar a /fnetcore/ (NO a loginClementeApp2) ────
        # El browser navega: login/index.html → loginClementeApp2.html → /fnetcore/
        # `loginClementeApp2.html` es un paso intermedio donde el JS de BBVA
        # llama postlogin y luego redirige a /fnetcore/.  En headless Chromium
        # ese paso a veces se atasca (el JS no termina), pero el postlogin SÍ
        # se ejecuta y las cookies de sesión quedan establecidas — entonces
        # podemos navegar a /fnetcore/ manualmente.
        from selenium.common.exceptions import TimeoutException

        def _is_logged_in(d):
            u = d.current_url or ""
            return ("/fnetcore/" in u
                    and "loginClementeApp2" not in u
                    and "login/index" not in u)

        try:
            WebDriverWait(driver, 45).until(_is_logged_in)
            logger.info("[bbva] navegación a /fnetcore/ OK — URL: %s",
                        (driver.current_url or "")[:200])
        except TimeoutException:
            cur = driver.current_url or ""
            logger.info("[bbva] timeout esperando /fnetcore/ — URL actual: %s", cur[:200])
            if "loginClementeApp2" in cur:
                # Atascado en el paso intermedio.  El postlogin probablemente ya
                # corrió (cookies establecidas), pero el JS no llegó a redirigir.
                # Forzamos la navegación a /fnetcore/.
                logger.info("[bbva] stuck en loginClementeApp2 — navegando a /fnetcore/ manualmente")
                try:
                    driver.get("https://online.bbva.com.ar/fnetcore/")
                    time.sleep(5)
                except Exception as nav_exc:
                    raise RuntimeError(f"[bbva] fallo navegando a /fnetcore/: {nav_exc}")
            elif "/login/" in cur or "login/index" in cur:
                self._dump_page_state(driver)
                raise RuntimeError(
                    f"[bbva] tras submit seguimos en /login/ (URL: {cur[:200]}). "
                    f"Posibles credenciales inválidas o captcha extra."
                )
            elif "desconexion" in cur or "logout" in cur:
                raise RuntimeError(
                    f"[bbva] tras submit el browser fue redirigido a desconexión "
                    f"({cur[:200]}). BBVA detectó la sesión como vencida — "
                    f"esto suele pasar si quedaron cookies stale, o si hubo "
                    f"demasiados intentos seguidos.  Reintentar en unos minutos."
                )
            else:
                self._dump_page_state(driver)
                raise RuntimeError(
                    f"[bbva] tras submit URL inesperada: {cur[:200]}"
                )

        post_url = driver.current_url or ""
        logger.info("[bbva] URL final: %s", post_url[:200])

        # Pequeña pausa para que la app Angular complete su inicialización
        time.sleep(3)

        # ── Paso 6: verificar sesión con datosperfil ──────────────────────────
        perf = self._api_request(driver, "/cliente/datosperfil")
        logger.info("[bbva] datosperfil HTTP %d  body[:200]=%s", perf["status"], perf["body"][:200])

        if perf["status"] == 200 and perf["json"]:
            perfil = ((perf["json"].get("result") or {}).get("perfilCliente", {}))
            nombre = perfil.get("nombre", "?")
            logger.info("[bbva] Login OK — usuario: %s", nombre)
            return

        raise RuntimeError(
            f"[bbva] datosperfil HTTP {perf['status']} tras login. URL: {post_url[:150]}. "
            f"Body: {perf['body'][:300]}"
        )

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva] %s", msg)
            log.append(msg)

        dias              = int(config.get("dias") or _DIAS_DEFAULT)
        usuario_default   = (config.get("usuario_default") or "").strip() or None
        # filtro_fecha_api: True (default) → BBVA filtra server-side, saldo=0 en respuesta.
        # False → fechas vacías en payload, BBVA devuelve saldo real por movimiento,
        # filtrado client-side.  Útil para dedup por saldo corriente.
        filtro_fecha_api  = bool(config.get("filtro_fecha_api", True))
        _log(f"Modo filtro_fecha_api={'server-side (saldo=0)' if filtro_fecha_api else 'client-side (saldo real)'}")

        # ── Determinar mapeo cuenta→fuente ────────────────────────────────────
        # Si el scheduler nos pasa `__cuentas__` (v0.4.0+): cada cuenta tiene
        # un product_key que matchea con la moneda BBVA (ARS/USD/EUR).
        #   product_key → MovimientoRaw.fuente
        # Si NO viene (legacy / standalone): caemos al esquema viejo basado en
        # `monedas` config string + fuente hardcoded "bbva_cuenta".
        cuentas_map = config.get("__cuentas__") or []
        if cuentas_map:
            product_to_fuente = {
                (c.get("product_key") or "").upper(): c.get("fuente")
                for c in cuentas_map if c.get("fuente")
            }
            monedas_permitidas = set(product_to_fuente.keys())
            _log(f"Modo multi-instancia — mapeo {product_to_fuente}")
        else:
            # Legacy: monedas config string, fuente fija
            _monedas_raw = (config.get("monedas") or "").strip()
            if _monedas_raw:
                monedas_permitidas = {
                    m.strip().upper() for m in _monedas_raw.split(",") if m.strip()
                }
            else:
                monedas_permitidas = {"ARS"}
            product_to_fuente = {m: "bbva_cuenta" for m in monedas_permitidas}
            _log(f"Modo legacy — monedas={sorted(monedas_permitidas)} → bbva_cuenta")

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
        _log(
            f"Cuentas encontradas en API: {len(cajas)}  |  "
            f"monedas a procesar: {sorted(monedas_permitidas)}  |  "
            f"usuario_default={usuario_default or '(none)'}"
        )

        today_art   = datetime.now(_ART).date()
        since_date  = today_art - timedelta(days=dias - 1)
        fecha_desde = since_date.strftime("%d/%m/%Y")
        fecha_hasta = today_art.strftime("%d/%m/%Y")
        _log(f"Rango: {fecha_desde} → {fecha_hasta} ({dias} días)")

        for cuenta in cajas:
            id_prod   = cuenta.get("id", "")
            alias     = cuenta.get("alias", id_prod)
            saldo_raw = cuenta.get("saldo") or cuenta.get("importe") or ""

            moneda = self._detect_moneda(cuenta, alias)

            # Registramos el saldo siempre (informativo, incluso si está filtrada)
            if saldo_raw:
                saldo_val = self.parse_amount(str(saldo_raw))
                fuente_target = product_to_fuente.get(moneda, "bbva_cuenta")
                saldo_key = "saldo_usd" if moneda == "USD" else "saldo_eur" if moneda == "EUR" else "saldo_ars"
                saldos.setdefault(fuente_target, {})[saldo_key] = saldo_val

            if moneda not in monedas_permitidas:
                _log(f"Saltando cuenta: {alias} (id={id_prod}, moneda={moneda} no mapeada)")
                continue

            fuente_target = product_to_fuente.get(moneda, "bbva_cuenta")
            _log(f"Procesando cuenta: {alias} (id={id_prod}, moneda={moneda}) → fuente={fuente_target}")
            if saldo_raw:
                _log(f"  Saldo actual: {saldo_raw}")

            movs = self._fetch_movimientos(
                driver, id_prod, fecha_desde, fecha_hasta, _log,
                moneda=moneda, usuario_default=usuario_default,
                fuente_target=fuente_target,
                filtro_fecha_api=filtro_fecha_api,
            )
            _log(f"  → {len(movs)} movimientos importados de {alias} (fuente={fuente_target})")
            movimientos.extend(movs)

        if config.get("auto_resumenes"):
            try:
                self._scrape_resumenes_cuenta(driver, config, _log)
            except Exception as exc:
                _log(f"✗ Error descargando resúmenes de cuenta: {exc}")
                logger.exception("[bbva] _scrape_resumenes_cuenta")

        return ScraperResult(
            fuente      = "bbva",
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    @staticmethod
    def _detect_moneda(cuenta: dict, alias: str) -> str:
        """
        Detecta la moneda de una cuenta BBVA.
        Prioriza el campo `codigoMoneda`/`moneda` de la API si está presente;
        si no, deduce por el alias ("Pesos"/"Dolares"/"Euros").  Default: ARS.
        """
        for k in ("codigoMoneda", "moneda", "currency"):
            v = cuenta.get(k)
            if v:
                s = str(v).strip().upper()
                # Normalizar: 032=ARS, 840=USD, 978=EUR (códigos ISO típicos
                # que usan algunos bancos), o el código de moneda directo.
                if s in ("ARS", "032", "$", "PESOS"):
                    return "ARS"
                if s in ("USD", "840", "USS", "DOLAR", "DOLARES", "DÓLARES"):
                    return "USD"
                if s in ("EUR", "978", "EUROS"):
                    return "EUR"
        # Fallback: deducir por alias
        a = (alias or "").strip().upper()
        if "DOLAR" in a or "DÓLAR" in a or "USD" in a:
            return "USD"
        if "EURO" in a or "EUR" in a:
            return "EUR"
        return "ARS"

    # ── paginación ─────────────────────────────────────────────────────────────

    def _fetch_movimientos(
        self,
        driver,
        id_producto: str,
        fecha_desde: str,
        fecha_hasta: str,
        log_fn,
        moneda: str = "ARS",
        usuario_default: Optional[str] = None,
        fuente_target: str = "bbva_cuenta",
        filtro_fecha_api: bool = True,
    ) -> list[MovimientoRaw]:
        """
        Pagina la API de movimientos hasta obtenerlos todos (vía fetch del browser).

        filtro_fecha_api=True (default):
            Incluye fechaDesde/fechaHasta en el payload → BBVA filtra server-side.
            Ventaja: trae solo el rango pedido.
            Desventaja: BBVA devuelve saldo=0,00 en cada movimiento (bug de API).

        filtro_fecha_api=False:
            Envía fechaDesde/fechaHasta vacíos → BBVA devuelve saldo real por movimiento.
            El filtrado de fechas se hace client-side (hit_out_of_range corta la paginación).
            Útil cuando se necesita el saldo corriente como discriminador de dedup.
        """
        all_movs: list[MovimientoRaw] = []
        ultimo = 0
        # Parsear fecha_desde a ISO para comparar contra los movimientos recibidos
        # y cortar la paginación cuando empecemos a recibir cosas fuera del rango.
        # fecha_desde está en formato DD/MM/YYYY.
        fecha_desde_iso = self.parse_date_ar(fecha_desde)

        while True:
            # Con filtro_fecha_api=True: BBVA filtra server-side (saldo=0 en respuesta).
            # Con filtro_fecha_api=False: fechas vacías → saldo real, filtrado client-side.
            payload: dict = {
                "idProducto":               id_producto,
                "ultimoMovimientoMostrado": "0" if ultimo == 0 else ultimo,
                "filtro":                   False,
                "fechaDesde":               fecha_desde if filtro_fecha_api else "",
                "fechaHasta":               fecha_hasta if filtro_fecha_api else "",
                "importeDesde":             "",
                "importeHasta":             "",
                "codigoTipoMovimiento":     "",
                "idRubroMovimiento":        "",
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
            # Diagnóstico: loguear keys del primer movimiento para confirmar
            # qué campos trae la API (útil para refinar detección de signo).
            if batch and ultimo == 0:
                log_fn(f"    [debug] keys del primer mov: {sorted(batch[0].keys())}")

            # Safety: filtrar movimientos fuera de fecha_desde — defensa por si
            # BBVA ignora el filtro de fechas en alguna página.  El batch viene
            # newest-first, así que el primero fuera de rango → todos los
            # siguientes también están fuera.
            batch_in_range = batch
            if fecha_desde_iso:
                in_range = []
                for mov in batch:
                    f_iso = self.parse_date_ar(mov.get("fecha", ""))
                    if f_iso and f_iso < fecha_desde_iso:
                        break   # fuera del rango → parar
                    in_range.append(mov)
                if len(in_range) < len(batch):
                    log_fn(
                        f"    [filter] descartados {len(batch) - len(in_range)} movimientos "
                        f"anteriores a {fecha_desde} (fuera del rango configurado)"
                    )
                batch_in_range = in_range
                # Si descartamos algo, no tiene sentido seguir paginando
                # (los siguientes son aún más viejos)
                hit_out_of_range = len(in_range) < len(batch)
            else:
                hit_out_of_range = False

            batch_movs = self._parse_batch(
                batch_in_range, log_fn,
                moneda=moneda, usuario_default=usuario_default,
                fuente_target=fuente_target,
            )
            self._enrich_with_detalle(driver, id_producto, batch_movs, log_fn)
            all_movs.extend(batch_movs)

            # Stop conditions:
            #   - llegamos al final de la página (menos de _PAGE_SIZE devueltos)
            #   - se cortó el batch porque entró movimientos fuera del rango
            if len(batch) < _PAGE_SIZE or hit_out_of_range:
                break

            ultimo += len(batch)

        return all_movs

    # ── detalle de movimiento ─────────────────────────────────────────────────
    #
    # BBVA expone distintos endpoints de detalle según el tipo de operación.
    # El campo `codigoAccionDetalleMovimientoCuenta` indica si el mov tiene
    # detalle, pero el endpoint correcto se deduce del campo `procedencia`:
    #
    #   procedencia = "OP\d+"  →  codigoAccion 02/03
    #     → POST /banelco/detalleservicio
    #     → devuelve: servicio (nombre del servicio), cajeroEntidad, hora,
    #                 numeroTarjeta, importe
    #     → codigoAccion=03: PAGO DE SERVICIOS TARJETA
    #     → codigoAccion=02: OPERACION EN EFECTIVO TARJE
    #
    #   codigoAccion=06, claveConcepto=136  →  transferencia inmediata saliente
    #     → POST /banelco/transferencias/detalleinmediataemitida
    #     → devuelve: cbuDestino (CBU, sin nombre)
    #     → no implementado aún (solo CBU, bajo valor para categorización)
    #
    #   codigoAccion=32/10/13/05/14: endpoints no confirmados por HAR aún.

    def _fetch_detalleservicio(
        self,
        driver,
        id_producto: str,
        mov: "MovimientoRaw",
        log_fn=None,
    ) -> Optional[dict]:
        """
        Llama a `/banelco/detalleservicio` para movimientos de pago de servicios
        (codigoAccion=02 OPERACION EFECTIVO TARJE, codigoAccion=03 PAGO SERVICIOS).

        Parámetros requeridos por la API (confirmados por HAR):
          idProducto, fecha (DD/MM/YYYY), claveConcepto, codigoTipoMovimiento,
          procedencia (e.g. "OP6561").

        Respuesta (campo `detalleMovBanelcoServicio`):
          servicio, cajeroEntidad, hora, numeroTarjeta, importe.
        """
        rd = mov.raw_data or {}
        # Convertir fecha ISO → DD/MM/YYYY
        try:
            from datetime import date as _date
            fecha_ar = _date.fromisoformat(mov.fecha).strftime("%d/%m/%Y")
        except Exception:
            fecha_ar = mov.fecha

        payload = {
            "idProducto":           id_producto,
            "fecha":                fecha_ar,
            "claveConcepto":        str(rd.get("clave_concepto")        or ""),
            "codigoTipoMovimiento": str(rd.get("codigo_tipo_movimiento") or ""),
            "procedencia":          str(rd.get("procedencia")           or "").strip(),
        }
        resp = self._api_request(
            driver,
            "/cliente/productos/cuentas/movimientos/banelco/detalleservicio",
            method="POST",
            json_body=payload,
            timeout=15,
        )
        if resp["status"] != 200:
            if log_fn:
                log_fn(
                    f"      [detalleservicio] HTTP {resp['status']} "
                    f"fecha={fecha_ar} proc={payload['procedencia']} — {resp['body'][:150]}"
                )
            return None

        detalle = ((resp["json"] or {}).get("result") or {}).get(
            "detalleMovBanelcoServicio"
        ) or {}
        if log_fn:
            log_fn(
                f"      [detalleservicio] {_json.dumps(detalle, ensure_ascii=False)[:300]}"
            )
        return detalle or None

    def _fetch_detalleinmediata(
        self,
        driver,
        id_producto: str,
        mov: "MovimientoRaw",
        log_fn=None,
    ) -> Optional[dict]:
        """
        POST /banelco/transferencias/detalleinmediataemitida
        Para codigoAccion=06 (TRANSFERENCIA saliente inmediata, claveConcepto=136).

        Parámetros (confirmados por HAR):
          idProducto, fecha (DD/MM/YYYY), claveConcepto, codigoTipoMovimiento,
          procedencia, importe (string original API), referencia, origen.

        Respuesta (campo `detalleMovBanelcoTransferenciaInmEmi`):
          cbuDestino — CBU de la cuenta destino (22 dígitos).
        """
        rd = mov.raw_data or {}
        try:
            from datetime import date as _date
            fecha_ar = _date.fromisoformat(mov.fecha).strftime("%d/%m/%Y")
        except Exception:
            fecha_ar = mov.fecha

        payload = {
            "idProducto":           id_producto,
            "fecha":                fecha_ar,
            "claveConcepto":        str(rd.get("clave_concepto")        or ""),
            "codigoTipoMovimiento": str(rd.get("codigo_tipo_movimiento") or ""),
            "procedencia":          str(rd.get("procedencia")           or "").strip(),
            "importe":              str(rd.get("importe_raw")           or ""),
            "referencia":           str(rd.get("referencia")            or ""),
            "origen":               str(rd.get("origen")               or ""),
        }
        resp = self._api_request(
            driver,
            "/cliente/productos/cuentas/movimientos/banelco/transferencias/detalleinmediataemitida",
            method="POST",
            json_body=payload,
            timeout=15,
        )
        if resp["status"] != 200:
            if log_fn:
                log_fn(
                    f"      [detalleinmediata] HTTP {resp['status']} "
                    f"fecha={fecha_ar} — {resp['body'][:150]}"
                )
            return None

        detalle = ((resp["json"] or {}).get("result") or {}).get(
            "detalleMovBanelcoTransferenciaInmEmi"
        ) or {}
        if log_fn:
            cbu = detalle.get("cbuDestino", "")
            log_fn(
                f"      [detalleinmediata] cbuDestino={cbu!r}  "
                f"{_json.dumps({k: v for k, v in detalle.items() if k != 'cbuDestino'}, ensure_ascii=False)}"
            )
        return detalle or None

    def _enrich_with_detalle(
        self,
        driver,
        id_producto: str,
        movs: list["MovimientoRaw"],
        log_fn=None,
    ) -> None:
        """
        Enriquece movimientos con datos del endpoint de detalle correspondiente.

        Ruteo:
          - procedencia ~ "OP\\d+"  →  _fetch_detalleservicio
              → agrega raw_data["servicio"] y lo incorpora a la descripción.
          - codigoAccion == "06"    →  _fetch_detalleinmediata
              → loguea y guarda raw_data["cbu_destino"].
        """
        for mov in movs:
            rd = mov.raw_data or {}
            codigo_accion = str(rd.get("codigo_accion_detalle") or "").strip()
            if not codigo_accion:
                continue

            procedencia = str(rd.get("procedencia") or "").strip()

            # Pagos de servicios: procedencia tiene patrón "OP\d+"
            if re.match(r"^OP\d+$", procedencia):
                detalle = self._fetch_detalleservicio(driver, id_producto, mov, log_fn)
                if not detalle:
                    continue
                servicio = (detalle.get("servicio") or "").strip()
                if servicio:
                    mov.raw_data["servicio"] = servicio
                    if servicio.upper() not in mov.descripcion.upper():
                        mov.descripcion = f"{mov.descripcion} — {servicio}"
                cajero = (detalle.get("cajeroEntidad") or "").strip()
                if cajero:
                    mov.raw_data["cajero_entidad"] = cajero
                hora = (detalle.get("hora") or "").strip()
                if hora:
                    mov.raw_data["hora_operacion"] = hora

            # Transferencias inmediatas salientes (codigoAccion=06)
            elif codigo_accion == "06":
                detalle = self._fetch_detalleinmediata(driver, id_producto, mov, log_fn)
                if detalle:
                    cbu = (detalle.get("cbuDestino") or "").strip()
                    if cbu:
                        mov.raw_data["cbu_destino"] = cbu

    # ── parsing de un batch ───────────────────────────────────────────────────

    @staticmethod
    def _detect_sign(mov: dict, mov_older: Optional[dict], importe_signed: float) -> tuple[int, str]:
        """
        Detecta el signo de un movimiento BBVA cuenta.
        Devuelve (sign, reason) donde sign ∈ {+1 egreso, -1 ingreso}.

        Estrategia (en orden de confiabilidad, basada en datos reales del
        endpoint `/cliente/productos/cuentas/movimientos`):

          1. Campo explícito de naturaleza/signo en la API (defensa por si
             futuras versiones de BBVA agregan uno: naturalezaMovimiento,
             naturaleza, signo, etc.).
          2. **`importe` firmado por la API** — fuente de verdad para este
             endpoint: `importe<0` = egreso, `importe>0` = ingreso.
             Confirmado experimentalmente (el log de v0.3.63 mostró importe
             negativo para egresos y positivo para ingresos).
          3. Comparación de saldos — para este endpoint NO sirve porque
             BBVA devuelve `saldo=0` en cada movimiento (sólo expone el saldo
             actual de la cuenta a nivel `cuentas`).  Lo dejamos por si en
             algún momento BBVA empieza a devolverlo.
          4. Default egreso (caso peor — sólo si importe es 0 y nada más
             aplica, lo cual no debería ocurrir).
        """
        # 1. Naturaleza / signo explícito (defensa para futuros cambios)
        for k in ("naturalezaMovimiento", "naturaleza", "signo", "tipoSigno",
                  "codigoSigno", "tipoNaturaleza", "indicadorMovimiento"):
            v = mov.get(k)
            if v is None or v == "":
                continue
            s = str(v).strip().upper()
            if s in ("C", "CR", "CREDITO", "CRÉDITO", "CREDIT", "+", "1", "I"):
                return (-1, f"{k}={v}")
            if s in ("D", "DB", "DEBITO", "DÉBITO", "DEBIT", "-", "0", "E"):
                return (+1, f"{k}={v}")

        # 2. **Importe firmado** — fuente de verdad para BBVA cuenta
        if importe_signed < 0:
            return (+1, "importe<0")
        if importe_signed > 0:
            return (-1, "importe>0")

        # 3. Comparación de saldos (no aplica en BBVA cuenta porque saldo=0,
        #    pero queda como fallback defensivo)
        if mov_older is not None:
            try:
                saldo_actual   = BbvaScraper._safe_parse_amount(mov.get("saldo"))
                saldo_anterior = BbvaScraper._safe_parse_amount(mov_older.get("saldo"))
                if (saldo_actual is not None and saldo_anterior is not None
                    and saldo_actual != saldo_anterior):
                    return ((-1, "saldo↑") if saldo_actual > saldo_anterior
                            else (+1, "saldo↓"))
            except Exception:
                pass

        # 4. Default
        return (+1, "default")

    @staticmethod
    def _safe_parse_amount(v) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            return BbvaScraper.parse_amount(str(v))
        except Exception:
            return None

    def _parse_batch(
        self,
        batch: list[dict],
        log_fn=None,
        moneda: str = "ARS",
        usuario_default: Optional[str] = None,
        fuente_target: str = "bbva_cuenta",
    ) -> list[MovimientoRaw]:
        """
        Convierte un batch de movimientos BBVA a MovimientoRaw.
        El array llega newest-first.  Ver `_detect_sign` para la lógica del signo.

        Args:
            moneda: código de moneda para los movimientos ("ARS"/"USD"/"EUR").
            usuario_default: si está seteado, se escribe en raw_data["usuario"]
                de cada movimiento, y `importar_a_gastos` lo aplica como el
                usuario del gasto creado.  None → no se setea (cae al fallback
                de user_config en importar_a_gastos).

        Convención de monto:
          monto > 0 = egreso   (plata que sale)
          monto < 0 = ingreso  (plata que entra)
        """
        result: list[MovimientoRaw] = []
        # Dedup within this batch: BBVA sometimes returns the same transaction
        # twice with different `concepto` values (e.g. "Transferencia inmediata"
        # AND "DB TRF INM COE Nro:XXXXXX").  The post-transaction balance (saldo)
        # is unique per real operation, so (fecha, abs_importe, saldo) is a
        # reliable same-transaction fingerprint.
        # "DB TRF INM" / "TRANSF DEBITO Nro:…" are TEMPORARY — BBVA replaces
        # them with the stable description after a few days.  When we see both,
        # keep the stable one.
        _seen_saldo: dict = {}  # key → index in result

        for i, mov in enumerate(batch):
            fecha = self.parse_date_ar(mov.get("fecha", ""))
            if not fecha:
                continue

            importe_str    = str(mov.get("importe", "0") or "0")
            importe_signed = self.parse_amount(importe_str)
            importe_abs    = abs(importe_signed)

            saldo_raw = mov.get("saldo")
            saldo_val = BbvaScraper._safe_parse_amount(str(saldo_raw)) if saldo_raw is not None else None
            concepto = (mov.get("concepto") or "").strip()
            canal    = (mov.get("canal")    or "").strip()
            desc     = concepto or canal or "Movimiento BBVA"

            # Solo deduplicar cuando el saldo es un valor real no-cero.
            # Cuando BBVA devuelve saldo=0,00 para todos los movimientos (que es
            # lo que hace en esta cuenta), la clave (fecha, abs_importe, 0.0) colisiona
            # entre un egreso y un ingreso del mismo monto el mismo día — p.ej.
            # un DEBITO DEBIN de $2.298.000 y un CR TRF INM COE de $2.298.000 en
            # la misma fecha quedan con la misma clave y el segundo se descarta.
            if saldo_val is not None and saldo_val != 0.0:
                _key = (fecha, round(importe_abs, 2), round(saldo_val, 2))
                if _key in _seen_saldo:
                    # Duplicate found — if the already-stored entry has a
                    # temporary description and this one is stable, replace it.
                    _is_temp = lambda d: d.startswith("DB TRF") or d.startswith("TRANSF DEBITO") or "Nro:" in d
                    prev_idx = _seen_saldo[_key]
                    if _is_temp(result[prev_idx].descripcion) and not _is_temp(desc):
                        result[prev_idx].descripcion = desc
                        if log_fn:
                            log_fn(
                                f"    [dup→stable] {fecha} {importe_abs:.2f} "
                                f"saldo={saldo_val:.2f} desc actualizada: {desc!r}"
                            )
                    else:
                        if log_fn:
                            log_fn(
                                f"    [skip dup] {fecha} {importe_abs:.2f} "
                                f"saldo={saldo_val:.2f} — concepto duplicado omitido"
                            )
                    continue
                _seen_saldo[_key] = len(result)  # will be appended below

            # mov_older = el siguiente en el array newest-first (= movimiento
            # inmediatamente anterior en el tiempo, su saldo es el "antes" del
            # actual).  Para el último mov del batch, no hay older disponible.
            mov_older = batch[i + 1] if i + 1 < len(batch) else None
            sign, reason = self._detect_sign(mov, mov_older, importe_signed)
            monto = importe_abs * sign

            denominacion_cuenta = (mov.get("denominacionCuenta") or "").strip()
            numero_cuenta       = (mov.get("numeroCuenta")       or "").strip()
            clave_operacion     = (mov.get("claveOperacion")     or "").strip()
            codigo_sucursal     = str(mov.get("codigoSucursal")  or "").strip()
            origen              = (mov.get("origen")             or "").strip()
            procedencia         = (mov.get("procedencia")        or "").strip()
            numero_cheque       = str(mov.get("numeroCheque")    or "").strip()
            codigo_accion       = str(mov.get("codigoAccionDetalleMovimientoCuenta") or "").strip()

            if log_fn:
                tag = "ingreso" if sign < 0 else "egreso"
                log_fn(
                    f"    mov fecha={fecha} importe={importe_signed:+.2f} "
                    f"saldo={mov.get('saldo')} → {tag} ({reason})"
                )
                extras = {
                    "denominacionCuenta": denominacion_cuenta,
                    "numeroCuenta":       numero_cuenta,
                    "claveOperacion":     clave_operacion,
                    "codigoSucursal":     codigo_sucursal,
                    "origen":             origen,
                    "procedencia":        procedencia,
                    "numeroCheque":       numero_cheque,
                    "codigoAccion":       codigo_accion,
                }
                extras_str = "  ".join(
                    f"{k}={v!r}" for k, v in extras.items() if v and v != "0"
                )
                if extras_str:
                    log_fn(f"      [extra] {extras_str}")

            raw_data = {
                "saldo":                  mov.get("saldo"),
                "canal":                  canal or None,
                "numero_operacion":       mov.get("numeroOperacion") or None,
                "referencia":             mov.get("referencia")      or None,
                "clave_concepto":         mov.get("claveConcepto")   or None,
                "clave_operacion":        clave_operacion or None,
                "codigo_tipo_movimiento": mov.get("codigoTipoMovimiento") or None,
                "codigo_sucursal":        codigo_sucursal or None,
                "codigo_accion_detalle":  codigo_accion or None,
                "denominacion_cuenta":    denominacion_cuenta or None,
                "numero_cuenta":          numero_cuenta or None,
                "origen":                 origen or None,
                "procedencia":            procedencia or None,
                "numero_cheque":          numero_cheque if numero_cheque and numero_cheque != "0" else None,
                "importe_raw":            importe_str,   # formato original API p/ endpoints de detalle
                "tiene_detalle":          mov.get("tieneDetalle"),
                "sign_reason":            reason,
                "usuario":                usuario_default,   # None si no hay config
            }
            # Limpiar None para no inflar el raw_data
            raw_data = {k: v for k, v in raw_data.items() if v is not None}

            result.append(MovimientoRaw(
                fuente      = fuente_target,
                fecha       = fecha,
                descripcion = desc,
                monto       = monto,
                moneda      = moneda,
                raw_data    = raw_data,
            ))

        return result

    # ── Auto-descarga de resúmenes PDF (Caja de Ahorro) ──────────────────────

    _EP_EXTRACTOS  = "/cliente/extractos/extractos"
    _EP_GETPDF     = "/cliente/extractos/getPdf"
    _EP_VIEWER_PDF = "/seguridad/viewerAdobePdf/verificacion"
    _SUMMARIES_URL = "https://online.bbva.com.ar/fnetcore/#/private/summaries"

    @staticmethod
    def _resumenes_window(config: dict) -> tuple:
        """
        Devuelve (cutoff_date, [years]) según el config 'resumenes_meses'.

        Se importan resúmenes con fechaCierre >= cutoff. `years` cubre el cruce de
        año (ej. en enero con meses=3 hay que consultar también el año anterior).
        Default 1 mes; se clampa a 1..24.
        """
        from datetime import date
        try:
            meses = int(str(config.get("resumenes_meses") or "1").strip())
        except (TypeError, ValueError):
            meses = 1
        meses = max(1, min(meses, 24))
        today = date.today()
        m, y = today.month - meses, today.year
        while m <= 0:
            m += 12
            y -= 1
        cutoff = date(y, m, 1)
        years  = list(range(cutoff.year, today.year + 1))
        return cutoff, years

    @staticmethod
    def _parse_cierre(s):
        """Parsea fechaCierre 'DD/MM/YYYY' a date; None si no parsea."""
        from datetime import datetime
        try:
            return datetime.strptime(str(s).strip(), "%d/%m/%Y").date()
        except Exception:
            return None

    def _fetch_extractos(self, driver, log_fn, years=None) -> list[dict]:
        """
        POST /extractos/extractos {"fecha":"YYYY"} → lista de resúmenes.
        Devuelve la lista de extractos (cada uno con 'reporte', 'fechaCierre', 'detalle').
        Si `years` trae varios años, consulta cada uno y concatena (para backfill que
        cruza el cambio de año). Default: solo el año actual.

        BBVA bloquea este endpoint (statusCode=500) si el SPA Angular no fue
        navegado a la sección "Resúmenes" primero.  El flujo que BBVA espera:
          1. driver.get(#/private/summaries) — el Angular router inicializa el módulo
          2. GET /seguridad/viewerAdobePdf/verificacion — gate check del módulo
          3. POST /extractos/extractos — ahora acepta la request
        """
        from datetime import datetime
        if years is None:
            years = [str(datetime.now().year)]
        else:
            years = [str(y) for y in years]

        log_fn("  [extractos] navegando a sección Resúmenes del SPA…")
        try:
            driver.get(self._SUMMARIES_URL)
            time.sleep(4)
        except Exception as exc:
            log_fn(f"  [extractos] aviso navegando: {exc}")

        self._api_request(driver, self._EP_VIEWER_PDF)

        all_extractos: list[dict] = []
        for year in years:
            resp = self._api_request(
                driver, self._EP_EXTRACTOS, method="POST", json_body={"fecha": year}
            )
            if resp["status"] != 200 or not resp["json"]:
                log_fn(f"  [extractos] año {year}: HTTP {resp['status']} — {resp['body'][:200]}")
                continue
            sc = str(resp["json"].get("statusCode") or "")
            extractos = ((resp["json"].get("result") or {}).get("extractos") or [])
            if extractos:
                log_fn(f"  [extractos] {len(extractos)} resúmenes en la API (año {year}):")
                for ex in extractos:
                    log_fn(f"    • {ex.get('detalle','?')} — cierre {ex.get('fechaCierre','?')} (reporte={ex.get('reporte','?')})")
            else:
                log_fn(f"  [extractos] año {year}: lista vacía (statusCode={sc}) — body: {resp['body'][:300]}")
            all_extractos.extend(extractos)
        return all_extractos

    def _fetch_pdf_bytes(self, driver, reporte: str, log_fn) -> Optional[bytes]:
        """
        POST /extractos/getPdf {"reporte":"..."} → bytes del PDF.
        Usa fetch() + arrayBuffer() dentro del browser y transfiere como base64.
        """
        import base64 as _b64
        ts  = str(int(time.time() * 1000))
        url = f"{_API_BASE}{self._EP_GETPDF}?ts={ts}&reporte={reporte}"

        js = """
        var url     = arguments[0];
        var reporte = arguments[1];
        var cb      = arguments[arguments.length - 1];

        var xsrf = null;
        try {
            document.cookie.split(';').forEach(function(c) {
                var p = c.trim();
                if (p.startsWith('XSRF-TOKEN='))
                    xsrf = decodeURIComponent(p.substring(11));
            });
        } catch(e) {}

        var opts = {
            method: 'POST',
            headers: {'Content-Type': 'application/json;charset=UTF-8', 'Accept': 'application/pdf, */*'},
            credentials: 'include',
            body: JSON.stringify({reporte: reporte})
        };
        if (xsrf) opts.headers['X-XSRF-TOKEN'] = xsrf;

        fetch(url, opts)
            .then(function(r) {
                return r.arrayBuffer().then(function(buf) {
                    if (!buf || buf.byteLength === 0) {
                        cb({status: r.status, base64: '', error: 'empty'});
                        return;
                    }
                    var bytes = new Uint8Array(buf);
                    var str = '';
                    var CHUNK = 8192;
                    for (var i = 0; i < bytes.length; i += CHUNK) {
                        str += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
                    }
                    cb({status: r.status, base64: btoa(str)});
                });
            })
            .catch(function(e) { cb({status: 0, base64: '', error: String(e)}); });
        """
        try:
            driver.set_script_timeout(60)
            result = driver.execute_async_script(js, url, reporte) or {}
        except Exception as exc:
            log_fn(f"  [getPdf] error ejecutando fetch: {exc}")
            return None

        if result.get("error") or result.get("status") != 200:
            log_fn(f"  [getPdf] HTTP {result.get('status')} error={result.get('error','')}")
            return None

        b64 = result.get("base64") or ""
        if not b64:
            log_fn("  [getPdf] respuesta vacía")
            return None
        try:
            pdf_bytes = _b64.b64decode(b64)
        except Exception as exc:
            log_fn(f"  [getPdf] error decodificando base64: {exc}")
            return None
        if not pdf_bytes.startswith(b"%PDF"):
            log_fn(f"  [getPdf] respuesta no es PDF: {pdf_bytes[:20]!r}")
            return None
        return pdf_bytes

    def _import_resumen(
        self,
        pdf_bytes: bytes,
        filename: str,
        parser_key: str,
        fuente_target: str,
        config: dict,
        log_fn,
    ) -> int:
        """
        Parsea un PDF de resumen e importa los gastos al DB.
        Devuelve el número de gastos insertados.
        """
        import io
        from collections import Counter
        from db import insert_gastos, _CC_FUENTES, importacion_exists
        from parsers import PARSERS
        from categorizer import categorize_by_rules
        from user_config import read_user_config
        from scrapers_db import consolidate_scraper_duplicates

        if parser_key not in PARSERS:
            log_fn(f"  [import] parser desconocido: {parser_key}")
            return 0
        if importacion_exists(fuente_target, filename):
            log_fn(f"  [import] {filename} ya importado")
            return 0

        try:
            gastos = PARSERS[parser_key].parse(io.BytesIO(pdf_bytes), filename)
        except Exception as exc:
            log_fn(f"  [import] error parseando {filename}: {exc}")
            return 0

        if not gastos:
            log_fn(f"  [import] {filename}: sin movimientos")
            return 0

        log_fn(f"  [import] {filename}: {len(gastos)} movimientos parseados")

        _fechas_tmp = [str(g.fecha)[:7] for g in gastos]
        mes_resumen_check = Counter(_fechas_tmp).most_common(1)[0][0] if _fechas_tmp else None
        if mes_resumen_check:
            from db import importacion_exists_mes, _conn as _db_conn
            if importacion_exists_mes(fuente_target, mes_resumen_check):
                log_fn(f"  [import] {filename}: mes {mes_resumen_check} ya importado manualmente — registrando stub y saliendo")
                with _db_conn() as _c:
                    _c.execute(
                        "INSERT INTO importaciones (fuente, archivo, mes_resumen, cantidad) VALUES (?,?,?,0)",
                        (fuente_target, filename, mes_resumen_check),
                    )
                return 0

        user_cfg        = read_user_config()
        usuario_default = user_cfg["fuente_usuario"].get(parser_key)
        reglas_usuario  = user_cfg.get("reglas_usuario", [])
        _usuarios       = user_cfg.get("usuarios", ["Titular", "Adicional"])
        _persona_map    = {}
        if len(_usuarios) > 0: _persona_map["Titular"]  = _usuarios[0]
        if len(_usuarios) > 1: _persona_map["Adicional"] = _usuarios[1]

        needs_flip = parser_key not in _CC_FUENTES

        records = []
        for g in gastos:
            eff_monto = -float(g.monto) if (needs_flip and g.monto != 0) else float(g.monto)
            cat = categorize_by_rules(g.descripcion, monto=eff_monto, fuente=fuente_target)
            fuente_cat = "regla" if cat else None
            d = g.model_dump()
            d["categoria"]        = cat
            d["categoria_fuente"] = fuente_cat
            d["fuente"]           = fuente_target
            if needs_flip and d["monto"] != 0:
                d["monto"] = -float(d["monto"])
            if g.usuario is not None:
                d["usuario"] = _persona_map.get(g.usuario, g.usuario)
            else:
                assigned = None
                if reglas_usuario:
                    desc_upper = g.descripcion.upper()
                    for rule in reglas_usuario:
                        palabras = rule.get("palabras", [])
                        if palabras and any(p.upper() in desc_upper for p in palabras):
                            assigned = rule.get("usuario") or None
                            break
                d["usuario"] = assigned if assigned else usuario_default
            records.append(d)

        fechas      = [str(r.get("fecha", ""))[:7] for r in records if r.get("fecha")]
        mes_resumen = Counter(fechas).most_common(1)[0][0] if fechas else None

        fecha_venc     = getattr(PARSERS[parser_key], "fecha_vencimiento", None)
        stmt_ars       = getattr(PARSERS[parser_key], "stmt_total_ars",    None)
        stmt_usd       = getattr(PARSERS[parser_key], "stmt_total_usd",    None)
        proximo_cierre = getattr(PARSERS[parser_key], "proximo_cierre",    None)
        proximo_venc   = getattr(PARSERS[parser_key], "proximo_venc",      None)

        import_info = {
            "fuente":         fuente_target,
            "archivo":        filename,
            "mes_resumen":    mes_resumen,
            "fecha_venc":     str(fecha_venc)     if fecha_venc     else None,
            "total_ars":      float(stmt_ars)      if stmt_ars       else None,
            "total_usd":      float(stmt_usd)      if stmt_usd       else None,
            "proximo_cierre": str(proximo_cierre)  if proximo_cierre else None,
            "proximo_venc":   str(proximo_venc)    if proximo_venc   else None,
        }
        count = insert_gastos(records, import_info=import_info)
        log_fn(f"  [import] {filename}: {count} gastos insertados (mes={mes_resumen})")

        _RESUMEN_PARSERS = frozenset({"amex", "bbva_mc", "bbva_visa", "bbva_cuenta"})
        if parser_key in _RESUMEN_PARSERS:
            deduped = consolidate_scraper_duplicates(fuente_target, records)
            if deduped:
                log_fn(f"  [import] {filename}: {deduped} duplicado(s) de scraper consolidados")

        return count

    def _scrape_resumenes_cuenta(self, driver, config: dict, log_fn) -> None:
        """
        Descarga e importa los resúmenes PDF de la Caja de Ahorro Pesos dentro de
        la ventana configurada ('resumenes_meses', default 1 = solo el más reciente).
        Los ya importados se saltean. Llamado desde scrape() cuando auto_resumenes
        está activo.
        """
        from datetime import date
        from db import importacion_exists

        cutoff, years = self._resumenes_window(config)
        log_fn(f"Buscando resúmenes PDF de Caja de Ahorro (desde {cutoff.isoformat()})…")
        extractos = self._fetch_extractos(driver, log_fn, years=years)
        if not extractos:
            return

        # Filtrar a CAJA DE AHORROS PESOS dentro de la ventana, más reciente primero
        candidatos = []
        for ex in extractos:
            detalle = (ex.get("detalle") or "").upper()
            reporte = (ex.get("reporte") or "").strip()
            if not reporte:
                continue
            if not ("CAJA DE AHORROS" in detalle and "PESOS" in detalle and "EUROS" not in detalle):
                continue
            cierre = self._parse_cierre(ex.get("fechaCierre"))
            if cierre and cierre < cutoff:
                continue
            candidatos.append((cierre or date.min, ex))
        candidatos.sort(key=lambda t: t[0], reverse=True)

        fuente_target = "bbva_cuenta"
        importados = 0
        for _cierre, ex in candidatos:
            reporte  = (ex.get("reporte") or "").strip()
            filename = f"BBVA_CUENTA_ARS_{reporte}_auto.pdf"

            if importacion_exists(fuente_target, filename):
                log_fn(f"  [cuenta] al día ({ex.get('fechaCierre')})")
                continue

            log_fn(f"  [cuenta] descargando resumen {ex.get('fechaCierre')} (reporte={reporte})…")
            pdf_bytes = self._fetch_pdf_bytes(driver, reporte, log_fn)
            if not pdf_bytes:
                continue

            log_fn(f"  [cuenta] PDF descargado ({len(pdf_bytes):,} bytes), importando…")
            self._import_resumen(pdf_bytes, filename, "bbva_cuenta", fuente_target, config, log_fn)
            importados += 1

        if importados:
            log_fn(f"  [cuenta] {importados} resumen(es) nuevos importados")

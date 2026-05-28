"""
Scraper BBVA Argentina — híbrido Selenium + httpx.

Estrategia de login (confirmada por análisis HAR):
  1. Selenium carga la página de login → Akamai Bot Manager inicializa cookies
     anti-bot en el browser real (no se puede replicar sin un browser verdadero).
  2. httpx extrae esas cookies y llama directamente a la API REST de login:
       POST /login/prelogin   → devuelve redirect URL con sessionIdLN
       POST /login/postlogin  → establece la sesión definitiva
  No se interactúa con el formulario HTML (web components Lit/Spherica que
  son extremadamente difíciles de automatizar en modo headless).

API base: https://online.bbva.com.ar/fnetcore/servicios/
Auth:     cookies de sesión de postlogin (jsessionid + otras).

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

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://online.bbva.com.ar/fnetcore/login/index.html"
_API_BASE  = "https://online.bbva.com.ar/fnetcore/servicios"

# Argentina — sin horario de verano
_ART = timezone(timedelta(hours=-3))

_DIAS_DEFAULT = 60
_PAGE_SIZE    = 10   # BBVA devuelve 10 movimientos por llamada (confirmado por HAR)

_HEADERS = {
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "es-AR,es;q=0.9",
    "Content-Type":     "application/json;charset=UTF-8",
    "Origin":           "https://online.bbva.com.ar",
    "Referer":          "https://online.bbva.com.ar/",
}

# versionFront: versión del bundle del login, enviada en el payload de prelogin.
# Valor confirmado por HAR del 2026-05-27.  Se intenta extraer del HTML en
# _extract_version_front(); si falla se usa este fallback.
_VERSION_FRONT_FALLBACK = "20260325.1526"

def _ts() -> str:
    """Cache-buster en milisegundos, igual que el frontend de BBVA."""
    return str(int(time.time() * 1000))


class BbvaScraper(BaseScraper):
    fuente       = "bbva"
    nombre       = "BBVA Argentina"
    login_origin = "https://online.bbva.com.ar"

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _driver_cookies(self, driver) -> dict[str, str]:
        """Extrae las cookies del WebDriver como dict plano para httpx."""
        return {c["name"]: c["value"] for c in driver.get_cookies()}

    def _make_client(self, cookies: dict[str, str]) -> httpx.Client:
        """httpx.Client preconfigurado con headers y cookies de sesión."""
        return httpx.Client(
            headers=_HEADERS,
            cookies=cookies,
            timeout=30,
            follow_redirects=True,
        )

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
        Extrae las cookies del driver y llama a datosperfil.
        No navega la SPA — sólo necesitamos las cookies para la API REST.
        """
        cookies = self._driver_cookies(driver)
        if not cookies:
            return False
        try:
            with self._make_client(cookies) as client:
                resp = client.get(
                    f"{_API_BASE}/cliente/datosperfil",
                    params={"ts": _ts()},
                )
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("result"))
        except Exception as exc:
            logger.info("[bbva] check_session: %s", exc)
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

          Paso 3 — postlogin:
            POST /login/postlogin con { numeroClienteAltamira, sessionIdLN }.
            Establece las cookies de sesión definitivas (jsessionid, etc.).

          Paso 4 — verificar:
            GET /cliente/datosperfil con las cookies combinadas.
        """
        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        # ── Paso 1: cargar página → Akamai inicializa cookies anti-bot ────────
        logger.info("[bbva] cargando login page para Akamai: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        time.sleep(6)   # tiempo para que los scripts de Akamai completen
        self._dump_page_state(driver)

        version_front   = self._extract_version_front(driver)
        cookies_akamai  = self._driver_cookies(driver)
        logger.info(
            "[bbva] Akamai cookies (%d): %s  |  versionFront: %s",
            len(cookies_akamai), sorted(cookies_akamai.keys()), version_front,
        )

        # ── Paso 2: POST prelogin ─────────────────────────────────────────────
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

        with self._make_client(cookies_akamai) as client:
            pre_resp = client.post(
                f"{_API_BASE}/login/prelogin",
                params={"ts": _ts()},
                json=prelogin_payload,
            )

        logger.info(
            "[bbva] prelogin HTTP %d  body=%s",
            pre_resp.status_code, pre_resp.text[:500],
        )

        if pre_resp.status_code != 200:
            raise RuntimeError(
                f"[bbva] prelogin HTTP {pre_resp.status_code}: {pre_resp.text[:300]}"
            )

        # ── Paso 3: parsear sessionIdLN y numeroClienteAltamira ───────────────
        # La respuesta incluye una URL de redirect con el formato:
        #   .../loginClementeApp2.html?TOKEN=/std/{numCliente}/0/{dni}//{sessionId}
        pre_cookies   = dict(pre_resp.cookies)
        all_cookies   = {**cookies_akamai, **pre_cookies}
        pre_result    = (pre_resp.json().get("result") or {})

        url_redirect  = ""
        for k in ("urlRedirect", "redirectUrl", "url", "redirect", "loginUrl", "callbackUrl"):
            v = str(pre_result.get(k, "") or "")
            if v and ("fnetcore" in v or "login" in v.lower()):
                url_redirect = v
                break

        logger.info("[bbva] url_redirect: %s", url_redirect[:150] if url_redirect else "(no detectado)")

        session_id     = ""
        numero_cliente = ""

        if url_redirect:
            # Formato: /std/{numCliente}/{algo}/{dni}//{sessionId}
            m = re.search(r"/std/(\d+)/\d+/\d+//([a-z0-9]+)", url_redirect)
            if m:
                numero_cliente = m.group(1)
                session_id     = m.group(2)

        # Fallback: buscar campos directos en el JSON
        if not session_id:
            session_id     = str(pre_result.get("sessionIdLN", "") or "")
            numero_cliente = str(pre_result.get("numeroClienteAltamira", "") or "")

        if not session_id:
            raise RuntimeError(
                f"[bbva] prelogin OK pero no se pudo extraer sessionId. "
                f"Campos en result: {list(pre_result.keys())}. "
                f"Body: {pre_resp.text[:400]}"
            )

        logger.info(
            "[bbva] sessionId (len=%d)  numeroCliente=%s",
            len(session_id), numero_cliente,
        )

        # ── Paso 4: POST postlogin ────────────────────────────────────────────
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
            "usuario":              "",
            "claveDigital":         "",
            "numeroClienteAltamira": numero_cliente,
            "sessionIdLN":           session_id,
        }

        with self._make_client(all_cookies) as client:
            post_resp = client.post(
                f"{_API_BASE}/login/postlogin",
                params={"ts": _ts()},
                json=postlogin_payload,
            )

        logger.info(
            "[bbva] postlogin HTTP %d  body=%s",
            post_resp.status_code, post_resp.text[:200],
        )
        post_cookies = dict(post_resp.cookies)
        all_cookies  = {**all_cookies, **post_cookies}

        # ── Paso 5: verificar sesión con datosperfil ──────────────────────────
        # Inyectar todas las cookies en el driver para que _save_session() las persista
        for name, value in all_cookies.items():
            try:
                driver.add_cookie({
                    "name":   name,
                    "value":  value,
                    "domain": "online.bbva.com.ar",
                    "path":   "/",
                })
            except Exception:
                pass

        with self._make_client(all_cookies) as client:
            perf_resp = client.get(
                f"{_API_BASE}/cliente/datosperfil",
                params={"ts": _ts()},
            )

        logger.info("[bbva] datosperfil HTTP %d", perf_resp.status_code)

        if perf_resp.status_code == 200:
            perfil = (
                (perf_resp.json().get("result") or {})
                .get("perfilCliente", {})
            )
            nombre = perfil.get("nombre", "?")
            logger.info("[bbva] Login OK — usuario: %s", nombre)
            return

        raise RuntimeError(
            f"[bbva] datosperfil HTTP {perf_resp.status_code} tras prelogin+postlogin. "
            f"postlogin body: {post_resp.text[:200]}. "
            f"datosperfil body: {perf_resp.text[:200]}"
        )

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva] %s", msg)
            log.append(msg)

        dias    = int(config.get("dias") or _DIAS_DEFAULT)
        cookies = self._driver_cookies(driver)

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        with self._make_client(cookies) as client:

            # ── Obtener lista de cuentas ──────────────────────────────────────
            resp = client.get(
                f"{_API_BASE}/cliente/productos/cuentas",
                params={"ts": _ts()},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"[bbva] cuentas HTTP {resp.status_code}: {resp.text[:200]}"
                )

            result = resp.json().get("result", {})
            cajas  = result.get("cajasAhorro", [])
            _log(f"Cuentas encontradas: {len(cajas)}")

            today_art  = datetime.now(_ART).date()
            since_date = today_art - timedelta(days=dias - 1)
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
                    client, id_prod, fecha_desde, fecha_hasta, _log
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
        client: httpx.Client,
        id_producto: str,
        fecha_desde: str,
        fecha_hasta: str,
        log_fn,
    ) -> list[MovimientoRaw]:
        """
        Pagina la API de movimientos hasta obtenerlos todos.

        Primera llamada: payload completo con fechaDesde/fechaHasta.
        Llamadas siguientes: sólo idProducto + ultimoMovimientoMostrado (int).
        La API devuelve ≤ 10 movimientos por página.
        """
        all_movs: list[MovimientoRaw] = []
        ultimo = 0

        while True:
            if ultimo == 0:
                payload: dict = {
                    "idProducto":              id_producto,
                    "ultimoMovimientoMostrado": "0",
                    "filtro":                  False,
                    "fechaDesde":              fecha_desde,
                    "fechaHasta":              fecha_hasta,
                    "importeDesde":            "",
                    "importeHasta":            "",
                    "codigoTipoMovimiento":    "",
                    "idRubroMovimiento":       "",
                }
            else:
                payload = {
                    "idProducto":              id_producto,
                    "ultimoMovimientoMostrado": ultimo,
                }

            resp = client.post(
                f"{_API_BASE}/cliente/productos/cuentas/movimientos",
                params={"ts": _ts()},
                json=payload,
            )
            if resp.status_code != 200:
                log_fn(
                    f"  movimientos HTTP {resp.status_code} — deteniendo paginación"
                )
                break

            data  = resp.json().get("result", {})
            count = data.get("count", 0)
            batch = data.get("movimientos", [])

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

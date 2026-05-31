"""
Scraper BBVA Argentina — Tarjetas de Crédito (Visa y Mastercard) vía Selenium.

Estrategia:
  1. LOGIN — idéntico al scraper de cuentas (bbva.py): interacción real con el
     formulario HTML, incluyendo el manejo de Akamai BotManager.
  2. SCRAPE — con la sesión activa, navega a la vista de "Mis Productos" de BBVA
     y extrae los movimientos del período en curso de cada tarjeta de crédito.
     Todo via DOM / Selenium, sin llamadas API directas.

Tarjetas soportadas:
  VISA (cualquier variante: Visa Signature, Visa Gold, etc.) → fuente "bbva_visa"
  MASTERCARD (Black, Gold, etc.)                             → fuente "bbva_mc"

El mapeo tarjeta→fuente se puede overridear vía __cuentas__ del scheduler
usando product_key="VISA" o product_key="MC".

Período: BBVA sólo muestra los movimientos del período en curso en la vista web,
por lo tanto el scraper no filtra por fecha — importa todo lo que renderiza.
"""

import logging
import re
import time
from typing import Optional

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://online.bbva.com.ar/fnetcore/login/index.html"
_BASE_URL  = "https://online.bbva.com.ar"

# Versión fallback del bundle de login (mismo que bbva.py)
_VERSION_FRONT_FALLBACK = "20260325.1526"

# Detecta tipo de tarjeta por el texto de la UI
_VISA_RE = re.compile(r"\bvisa\b", re.IGNORECASE)
_MC_RE   = re.compile(r"\bmastercard\b|\bmaster\b", re.IGNORECASE)

# Fuentes fijas cuando no hay __cuentas__ override
_FUENTE_VISA = "bbva_visa"
_FUENTE_MC   = "bbva_mc"


class BbvaTarjetasScraper(BaseScraper):
    fuente              = "bbva_tarjetas"
    nombre              = "BBVA Argentina — Tarjetas de Crédito"
    login_origin        = "https://online.bbva.com.ar"
    session_ttl_seconds = 240   # BBVA expira sesión en ~5 min; mismo margen que cuentas

    # ── Helpers de formulario ─────────────────────────────────────────────────

    def _type_input(self, driver, element, value: str) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.3)
            ActionChains(driver).click(element).send_keys(value).perform()
            return
        except Exception as e1:
            logger.info("[bbva-tj] _type_input estrategia 1 falló (%s), probando JS", e1)
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
                } catch(e) { el.value = val; }
                ['input', 'change', 'blur'].forEach(function(t) {
                    el.dispatchEvent(new Event(t, {bubbles: true, cancelable: true}));
                });
                """,
                element, value,
            )
            return
        except Exception as e2:
            logger.info("[bbva-tj] _type_input estrategia 2 falló (%s), probando fallback", e2)
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input',  {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            element, value,
        )

    def _click_element(self, driver, element) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.2)
            ActionChains(driver).move_to_element(element).click().perform()
            return
        except Exception as e1:
            logger.info("[bbva-tj] _click_element estrategia 1 falló (%s), probando JS", e1)
        driver.execute_script("arguments[0].click();", element)

    def _dump_page_state(self, driver) -> None:
        try:
            logger.info("[bbva-tj-diag] Título: %r", driver.title)
            logger.info("[bbva-tj-diag] URL: %s", driver.current_url)
            try:
                body = driver.execute_script(
                    "return document.body ? document.body.innerHTML.slice(0,1000) : '(sin body)'"
                )
                logger.info("[bbva-tj-diag] body[:1000]: %s", body)
            except Exception:
                pass
        except Exception as exc:
            logger.info("[bbva-tj-diag] error en dump: %s", exc)

    # ── check_session ─────────────────────────────────────────────────────────

    def check_session(self, driver) -> bool:
        """
        Navega al dashboard de BBVA y verifica que la app Angular haya cargado
        y el usuario esté logueado (no redirigido al login).
        """
        try:
            cur = driver.current_url or ""
            if "bbva.com.ar" not in cur:
                driver.get(f"{_BASE_URL}/fnetcore/")
                time.sleep(4)
            else:
                driver.get(f"{_BASE_URL}/fnetcore/")
                time.sleep(4)

            cur = driver.current_url or ""
            logger.info("[bbva-tj] check_session URL: %s", cur[:150])

            # Si redirigió al login → sesión expirada
            if "login" in cur.lower() or "desconexion" in cur.lower():
                return False

            # Esperar a que la app Angular monte algún elemento conocido del dashboard
            for _ in range(10):
                el = self.find(driver,
                    "[id='@bbva/global-position'], "
                    "[id='@bbva/cards'], "
                    "bbva-web-global-position, "
                    "[class*='global-position'], "
                    "[class*='globalPosition']"
                )
                if el:
                    return True
                time.sleep(1)

            # Si no encontramos el elemento del dashboard pero tampoco estamos en
            # /login/, puede que la SPA todavía esté cargando. Verificar URL final.
            cur = driver.current_url or ""
            return "login" not in cur.lower() and "desconexion" not in cur.lower()

        except Exception as exc:
            logger.info("[bbva-tj] check_session error: %s", exc)
            return False

    # ── do_login ──────────────────────────────────────────────────────────────

    def do_login(self, driver, config: dict) -> None:
        """Idéntico al login de BbvaScraper (bbva.py)."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException

        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        # Limpiar cookies stale
        try:
            cur = driver.current_url or ""
            if "bbva.com.ar" not in cur:
                driver.get("https://online.bbva.com.ar/")
                time.sleep(1)
            driver.delete_all_cookies()
            logger.info("[bbva-tj] cookies stale eliminadas")
        except Exception as exc:
            logger.info("[bbva-tj] no se pudieron eliminar cookies: %s", exc)

        # Cargar página de login y esperar Akamai+Adobe
        logger.info("[bbva-tj] cargando login: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        for _w in range(15):
            time.sleep(1)
            _ck = {c["name"] for c in driver.get_cookies()}
            if "_abck" in _ck and "s_visit" in _ck:
                logger.info("[bbva-tj] Akamai+Adobe cookies listas tras %ds", _w + 1)
                break
        else:
            logger.info("[bbva-tj] timeout esperando cookies Akamai (continuando)")

        # Localizar los 3 inputs
        try:
            dni_input = WebDriverWait(driver, 15).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "input[type='number']")
            )
        except Exception as exc:
            self._dump_page_state(driver)
            raise RuntimeError(f"[bbva-tj] no se encontró el input de DNI: {exc}")

        try:
            user_input = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            pass_input = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        except Exception as exc:
            self._dump_page_state(driver)
            raise RuntimeError(f"[bbva-tj] no se encontraron inputs usuario/password: {exc}")

        logger.info("[bbva-tj] inputs encontrados — llenando formulario")
        self._type_input(driver, dni_input,  dni)
        self._type_input(driver, user_input, username)
        self._type_input(driver, pass_input, password)

        # Botón submit
        submit_el = None
        for sel in [
            "form#login button[type='submit']",
            "button[type='submit']",
            "form button:last-of-type",
        ]:
            try:
                submit_el = driver.find_element(By.CSS_SELECTOR, sel)
                if submit_el:
                    logger.info("[bbva-tj] botón submit: %s", sel)
                    break
            except Exception:
                continue

        if submit_el is None:
            self._dump_page_state(driver)
            raise RuntimeError("[bbva-tj] no se encontró el botón submit")

        self._click_element(driver, submit_el)
        logger.info("[bbva-tj] submit clickeado — esperando navegación a /fnetcore/")

        def _is_logged_in(d):
            u = d.current_url or ""
            return ("/fnetcore/" in u
                    and "loginClementeApp2" not in u
                    and "login/index" not in u)

        try:
            WebDriverWait(driver, 45).until(_is_logged_in)
            logger.info("[bbva-tj] navegación a /fnetcore/ OK: %s",
                        (driver.current_url or "")[:200])
        except TimeoutException:
            cur = driver.current_url or ""
            logger.info("[bbva-tj] timeout — URL actual: %s", cur[:200])
            if "loginClementeApp2" in cur:
                logger.info("[bbva-tj] stuck en loginClementeApp2 — forzando /fnetcore/")
                try:
                    driver.get("https://online.bbva.com.ar/fnetcore/")
                    time.sleep(5)
                except Exception as nav_exc:
                    raise RuntimeError(f"[bbva-tj] fallo navegando a /fnetcore/: {nav_exc}")
            elif "/login/" in cur:
                self._dump_page_state(driver)
                raise RuntimeError(
                    f"[bbva-tj] tras submit seguimos en /login/ ({cur[:200]}). "
                    "Posibles credenciales inválidas o captcha extra."
                )
            else:
                self._dump_page_state(driver)
                raise RuntimeError(f"[bbva-tj] URL inesperada tras login: {cur[:200]}")

        # Pausa para que Angular complete su inicialización
        time.sleep(4)
        logger.info("[bbva-tj] Login OK — URL final: %s", (driver.current_url or "")[:150])

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva-tj] %s", msg)
            log.append(msg)

        # Resolver fuentes por product_key (multi-instancia) o usar defaults.
        # Siempre parte con los defaults (VISA→bbva_visa, MC→bbva_mc) y luego
        # los __cuentas__ del scheduler los sobreescriben para los tipos mapeados.
        # Así, si solo hay una cuenta linkeada (ej. VISA), MC sigue usando el default.
        product_to_fuente: dict[str, str] = {"VISA": _FUENTE_VISA, "MC": _FUENTE_MC}
        cuentas_map = config.get("__cuentas__") or []
        if cuentas_map:
            for c in cuentas_map:
                pk = (c.get("product_key") or "").upper()
                if pk and c.get("fuente"):
                    product_to_fuente[pk] = c["fuente"]
            _log(f"Modo multi-instancia — mapeo final: {product_to_fuente}")
        else:
            _log(f"Modo default — mapeo: {product_to_fuente}")

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # Detectar usuario adicional configurado
        usuario_default = (config.get("usuario_default") or "").strip() or None

        # Navegar al dashboard y encontrar las tarjetas de crédito
        cards = self._find_credit_cards(driver, _log)
        _log(f"Tarjetas encontradas: {len(cards)}")

        for card in cards:
            tipo   = card["tipo"]    # "VISA" o "MC"
            nombre = card["nombre"]
            fuente = product_to_fuente.get(tipo)
            if not fuente:
                _log(f"  Saltando {nombre} (tipo={tipo} sin mapeo de fuente)")
                continue

            _log(f"  Procesando {nombre} → fuente={fuente}")
            try:
                movs, saldo = self._scrape_card(driver, card, fuente, usuario_default, _log)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos[fuente] = {"saldo_ars": saldo}
                _log(f"  → {len(movs)} movimientos, saldo={saldo}")
            except Exception as exc:
                _log(f"  ✗ Error scrapeando {nombre}: {exc}")
                logger.exception("[bbva-tj] Error en _scrape_card para %s", nombre)

        return ScraperResult(
            fuente      = self.fuente,
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    # ── Detección de tarjetas ─────────────────────────────────────────────────

    # JS que recorre todo el DOM incluyendo shadow roots de Lit/Web Components.
    # Devuelve lista de {href, text, tag} para todos los <a> y elementos
    # clicables encontrados en cualquier nivel de shadow DOM.
    _JS_FIND_LINKS = """
    (function() {
        var results = [];
        var seen = new Set();
        function traverse(root) {
            if (!root) return;
            // Links y elementos navegables
            var links;
            try { links = root.querySelectorAll('a, [role="link"]'); } catch(e) { links = []; }
            for (var i = 0; i < links.length; i++) {
                var a = links[i];
                var href = a.href || a.getAttribute('href') || '';
                var text = (a.innerText || a.textContent || '').trim().slice(0, 150);
                var key  = href + '|' + text.slice(0, 40);
                if (!seen.has(key) && (href || text)) {
                    seen.add(key);
                    results.push({href: href, text: text, tag: (a.tagName||'').toLowerCase()});
                }
            }
            // Recorrer shadow roots
            var all;
            try { all = root.querySelectorAll('*'); } catch(e) { all = []; }
            for (var j = 0; j < all.length; j++) {
                if (all[j].shadowRoot) traverse(all[j].shadowRoot);
            }
        }
        traverse(document.body);
        return results;
    })();
    """

    # JS que extrae el texto completo del DOM incluyendo shadow roots.
    # Útil para verificar si "visa" / "mastercard" aparecen en algún lugar.
    _JS_DEEP_TEXT = """
    (function() {
        var parts = [];
        function traverse(root) {
            if (!root) return;
            try {
                var t = root.innerText || root.textContent || '';
                if (t.trim()) parts.push(t.trim().slice(0, 200));
            } catch(e) {}
            var all;
            try { all = root.querySelectorAll('*'); } catch(e) { all = []; }
            for (var i = 0; i < all.length; i++) {
                if (all[i].shadowRoot) traverse(all[i].shadowRoot);
            }
        }
        traverse(document.body);
        return parts.join(' ');
    })();
    """

    # JS que devuelve el innerHTML del MFE de posición global + sus shadow roots
    _JS_GP_DUMP = """
    (function() {
        var gp = document.getElementById('@bbva/global-position');
        var root = gp || document.body;
        var parts = [root.innerHTML ? root.innerHTML.slice(0, 3000) : ''];
        function shadowDump(node, depth) {
            if (depth > 6) return;
            var all;
            try { all = node.querySelectorAll('*'); } catch(e) { return; }
            for (var i = 0; i < all.length && parts.join('').length < 8000; i++) {
                if (all[i].shadowRoot) {
                    parts.push('<!--shadow:' + (all[i].tagName||'?') + '-->');
                    parts.push(all[i].shadowRoot.innerHTML.slice(0, 800));
                    shadowDump(all[i].shadowRoot, depth + 1);
                }
            }
        }
        shadowDump(root, 0);
        return parts.join('');
    })();
    """

    def _find_credit_cards(self, driver, log_fn) -> list[dict]:
        """
        Navega al dashboard de BBVA y busca las tarjetas de crédito visibles.

        Devuelve lista de dicts:
          {"tipo": "VISA"|"MC", "nombre": str, "url": str|None}

        Estrategia:
          A. Esperar que el MFE @bbva/global-position renderice contenido real,
             usando JS para verificar el tamaño del innerHTML.
          B. Recorrer TODO el shadow DOM via JS para encontrar links con texto
             "visa" o "mastercard".
          C. Si hay texto pero no links: hacer click sobre el primer elemento
             que mencione "visa"/"mastercard" y observar a qué URL navega.
          D. Log de diagnóstico amplio para calibrar si nada funciona.
        """
        log_fn("Navegando al dashboard…")
        driver.get(f"{_BASE_URL}/fnetcore/#/globalposition")

        # ── A. Esperar que el MFE renderice contenido (hasta 25s) ────────────
        # El MFE @bbva/global-position tarda varios segundos en montar.
        # Lo detectamos por el tamaño del innerHTML del div contenedor.
        for i in range(25):
            try:
                length = driver.execute_script(
                    "var el = document.getElementById('@bbva/global-position');"
                    "return el ? el.innerHTML.length : 0;"
                )
                if length and length > 500:
                    log_fn(f"MFE global-position listo ({length} chars) tras {i+1}s")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            log_fn("Timeout esperando MFE global-position (continuando igual)")

        # Pausa extra para shadow DOM
        time.sleep(3)
        log_fn(f"URL: {(driver.current_url or '')[:150]}")

        # ── Dump diagnóstico (shadow DOM incluido) ────────────────────────────
        try:
            dump = driver.execute_script(self._JS_GP_DUMP) or ""
            log_fn(f"[diag] DOM global-position+shadow[:8000]: {dump[:8000]}")
        except Exception as exc:
            log_fn(f"[diag] dump error: {exc}")

        # ── B. Buscar links con texto Visa/MC en todo el shadow DOM ──────────
        try:
            all_links = driver.execute_script(self._JS_FIND_LINKS) or []
            log_fn(f"[diag] Total links en shadow DOM: {len(all_links)}")
            log_fn(f"[diag] Primeros 20 links: {all_links[:20]}")
        except Exception as exc:
            log_fn(f"[diag] JS_FIND_LINKS error: {exc}")
            all_links = []

        cards: list[dict] = []
        seen: set[str] = set()

        for item in all_links:
            text = (item.get("text") or "").strip()
            href = (item.get("href") or "").strip()
            tipo = None
            if _VISA_RE.search(text):
                tipo = "VISA"
            elif _MC_RE.search(text):
                tipo = "MC"
            else:
                continue

            key = href or text[:40]
            if key in seen:
                continue
            seen.add(key)
            nombre = text.split("\n")[0].strip()[:80]
            cards.append({"tipo": tipo, "nombre": nombre, "url": href or None})
            log_fn(f"  [B] Encontrada: {tipo} — {nombre!r} → {href[:80]}")

        if cards:
            return cards

        # ── C. Texto sin link: verificar qué texto hay y hacer click ─────────
        try:
            deep_text = driver.execute_script(self._JS_DEEP_TEXT) or ""
            log_fn(f"[diag] Texto completo (shadow, primeros 3000 chars): {deep_text[:3000]}")
        except Exception as exc:
            log_fn(f"[diag] JS_DEEP_TEXT error: {exc}")
            deep_text = ""

        # Si hay texto de tarjeta en el DOM, intentar click-y-observar
        if _VISA_RE.search(deep_text) or _MC_RE.search(deep_text):
            log_fn("Texto de tarjeta detectado — intentando click-y-observar URL…")
            cards = self._find_cards_by_clicking(driver, log_fn)
            if cards:
                return cards

        # ── D. Nada encontrado — dejar log para diagnóstico manual ───────────
        log_fn(
            "⚠ No se encontraron tarjetas. Revisar el [diag] del DOM para "
            "identificar los selectores correctos de este BBVA build."
        )
        return []

    def _find_cards_by_clicking(self, driver, log_fn) -> list[dict]:
        """
        Estrategia de último recurso: busca en el shadow DOM CUALQUIER elemento
        cuyo innerText contenga "visa" o "mastercard", hace click en él y observa
        a qué URL navegó el browser. Esa URL se usa como destino de la tarjeta.
        """
        # JS que devuelve el elemento más pequeño (leaf) con texto Visa/MC
        js_find_el = """
        (function(pattern) {
            var re = new RegExp(pattern, 'i');
            var best = null;
            function traverse(root) {
                var all;
                try { all = root.querySelectorAll('*'); } catch(e) { return; }
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var t  = (el.innerText || el.textContent || '').trim();
                    if (re.test(t) && t.length < 200) {
                        // Preferir el elemento más pequeño (menos texto = más específico)
                        if (!best || t.length < (best._len || 9999)) {
                            el._len = t.length;
                            best = el;
                        }
                    }
                    if (el.shadowRoot) traverse(el.shadowRoot);
                }
            }
            traverse(document.body);
            return best;
        })(arguments[0]);
        """

        cards = []
        for tipo, pattern in [("VISA", r"visa"), ("MC", r"mastercard|master\b")]:
            try:
                url_before = driver.current_url or ""
                el = driver.execute_script(js_find_el, pattern)
                if not el:
                    log_fn(f"  [C] No se encontró elemento con texto '{pattern}'")
                    continue

                text = driver.execute_script(
                    "return (arguments[0].innerText || arguments[0].textContent || '').trim()", el
                ) or ""
                log_fn(f"  [C] Elemento encontrado para {tipo}: {text[:60]!r}")

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", el)
                time.sleep(4)

                url_after = driver.current_url or ""
                log_fn(f"  [C] URL tras click: {url_after[:150]}")

                if url_after != url_before and "login" not in url_after.lower():
                    nombre = text.split("\n")[0].strip()[:80] or (
                        "Tarjeta Visa" if tipo == "VISA" else "Tarjeta Mastercard"
                    )
                    cards.append({"tipo": tipo, "nombre": nombre, "url": url_after})
                    # Volver al dashboard para buscar la siguiente tarjeta
                    driver.get(f"{_BASE_URL}/fnetcore/#/globalposition")
                    time.sleep(5)
                else:
                    log_fn(f"  [C] URL no cambió tras click en {tipo} — puede ser modal")
                    # Si abrió un modal, intentar extraer el URL del panel activo
                    cur = driver.current_url or ""
                    if url_after == url_before:
                        # Buscar si hay un panel/modal abierto y capturar su URL interna
                        nombre = "Tarjeta Visa" if tipo == "VISA" else "Tarjeta Mastercard"
                        cards.append({"tipo": tipo, "nombre": nombre, "url": None, "_modal": True})

            except Exception as exc:
                log_fn(f"  [C] Error en click para {tipo}: {exc}")

        return cards

    # ── Scraping de una tarjeta ───────────────────────────────────────────────

    def _scrape_card(
        self,
        driver,
        card: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:
        """
        Navega a la tarjeta y extrae los movimientos del período en curso.
        Devuelve (movimientos, saldo_ars|None).
        """
        nombre = card["nombre"]
        url    = card.get("url")

        # Navegar a la tarjeta (si tenemos URL directa)
        if url:
            log_fn(f"  Navegando a {url[:100]}")
            driver.get(url)
            time.sleep(4)
        elif card.get("_modal"):
            # La tarjeta se abrió como modal — el contenido ya está en pantalla.
            # El scraper ya hizo el click en _find_cards_by_clicking.
            log_fn("  Modo modal — extrayendo de la vista actual")
        else:
            log_fn("  Sin URL ni modo modal — saltando")
            return [], None

        # Esperar que el contenido de movimientos renderice (shadow DOM incluido)
        # Verificamos via JS si hay texto de movimiento en el DOM profundo.
        for i in range(15):
            try:
                deep = driver.execute_script(self._JS_DEEP_TEXT) or ""
                # Heurística: si hay al menos 3 fechas DD/MM → probablemente cargó
                fechas = re.findall(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", deep)
                if len(fechas) >= 3:
                    log_fn(f"  Contenido de movimientos detectado tras {i+1}s ({len(fechas)} fechas)")
                    break
            except Exception:
                pass
            time.sleep(1)

        log_fn(f"  URL detalle: {(driver.current_url or '')[:150]}")

        # Diagnóstico del DOM (shadow incluido)
        try:
            dump = driver.execute_script(self._JS_GP_DUMP) or ""
            log_fn(f"  [diag] DOM tarjeta+shadow[:8000]: {dump[:8000]}")
        except Exception as exc:
            log_fn(f"  [diag] dump error: {exc}")

        saldo = self._extract_saldo(driver, log_fn)
        movimientos = self._extract_movimientos(driver, fuente, usuario_default, log_fn, nombre)
        return movimientos, saldo

    # ── Extracción de saldo ───────────────────────────────────────────────────

    def _extract_saldo(self, driver, log_fn) -> Optional[float]:
        """
        Intenta leer el saldo total a pagar usando el texto profundo del shadow DOM.
        Busca el primer importe monetario grande que aparezca en la cabecera.
        """
        try:
            deep_text = driver.execute_script(self._JS_DEEP_TEXT) or ""
            # Buscar montos en formato argentino: ej. "123.456,78" o "1.234,56"
            amounts = re.findall(r"[\d]{1,3}(?:[.]\d{3})*,\d{2}", deep_text.replace("\xa0", ""))
            if amounts:
                # Elegir el monto más grande (probablemente el saldo total)
                vals = []
                for a in amounts:
                    v = self.parse_amount(a)
                    if v and v > 0:
                        vals.append(v)
                if vals:
                    saldo = max(vals)
                    log_fn(f"  Saldo detectado: {saldo:.2f} (candidatos: {vals[:5]})")
                    return saldo
        except Exception as exc:
            log_fn(f"  Saldo error: {exc}")
        log_fn("  Saldo no detectado")
        return None

    # JS que extrae los movimientos de BBVA usando shadow DOM traversal.
    # BBVA Argentina renderiza cada movimiento como un web component con
    # atributos de datos (date, concept/description, amount) O como un
    # elemento de lista con sub-elementos de fecha/concepto/importe.
    # Este JS recorre toda la jerarquía shadow DOM y devuelve lo que encuentra.
    _JS_EXTRACT_MOVEMENTS = """
    (function() {
        var results = [];
        var dateRe   = /^\\d{1,2}[\\/-]\\d{1,2}([\\/-]\\d{2,4})?$|^\\d{4}-\\d{2}-\\d{2}$|^\\d{1,2}-[A-Za-z]{3}-\\d{2,4}$/;
        var amountRe = /^-?[\\d.]+,[\\d]{2}$|^-?[\\d]+,[\\d]{2}$/;

        function getAttr(el, names) {
            for (var i = 0; i < names.length; i++) {
                var v = el.getAttribute(names[i]);
                if (v && v.trim()) return v.trim();
            }
            return '';
        }

        function traverse(root) {
            if (!root) return;
            var all;
            try { all = root.querySelectorAll('*'); } catch(e) { return; }

            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var tag = (el.tagName || '').toLowerCase();

                // ── Estrategia 1: web component con atributos de datos ──────────
                if (tag.indexOf('bbva') >= 0 || tag.indexOf('movement') >= 0) {
                    var fecha  = getAttr(el, ['date','transaction-date','fecha','purchase-date']);
                    var desc   = getAttr(el, ['concept','description','descripcion','title','name']);
                    var amount = getAttr(el, ['amount','monto','importe','total']);
                    if ((fecha && dateRe.test(fecha)) && (amount && amountRe.test(amount))) {
                        results.push({fecha: fecha, desc: desc, amount: amount, src: 'attr:'+tag});
                        continue;
                    }
                }

                // ── Estrategia 2: shadow DOM (li, div, tr con texto de mov.) ──
                if (el.shadowRoot) {
                    traverse(el.shadowRoot);
                }
            }

            // ── Estrategia 3: texto directo de elementos tipo lista ───────────
            // Buscar <li> o divs donde el texto completo parezca un movimiento
            var candidates;
            try {
                candidates = root.querySelectorAll(
                    'li, [class*="movement-item"], [class*="MovementItem"], ' +
                    '[class*="transaction-item"], [class*="TransactionItem"], ' +
                    '[class*="movimiento-item"], [class*="consumo-item"]'
                );
            } catch(e) { candidates = []; }

            for (var j = 0; j < candidates.length; j++) {
                var cel = candidates[j];
                var text = (cel.innerText || cel.textContent || '').trim();
                if (!text || text.length > 500 || text.length < 5) continue;

                var lines = text.split(/\\n|\\r/).map(function(l){return l.trim();}).filter(Boolean);
                if (lines.length < 2) continue;

                // Buscar fecha (DD/MM o DD/MM/YYYY) y monto ($X.XXX,XX) en las líneas
                var fechaL  = '';
                var descL   = '';
                var amountL = '';

                for (var k = 0; k < lines.length; k++) {
                    var l = lines[k];
                    if (!fechaL && dateRe.test(l)) { fechaL = l; continue; }
                    if (!amountL && /[\\d.,]{4,}/.test(l) && /,\\d{2}$/.test(l)) { amountL = l; continue; }
                    if (!descL && l.length > 2 && !dateRe.test(l)) { descL = l; }
                }

                if (fechaL && (descL || amountL)) {
                    results.push({fecha: fechaL, desc: descL, amount: amountL, src: 'text'});
                }
            }
        }

        traverse(document.body);

        // Deduplicar por fecha+desc+amount
        var seen = {};
        var unique = [];
        results.forEach(function(r) {
            var key = r.fecha + '|' + r.desc + '|' + r.amount;
            if (!seen[key]) { seen[key] = true; unique.push(r); }
        });
        return unique;
    })();
    """

    # ── Extracción de movimientos ─────────────────────────────────────────────

    def _extract_movimientos(
        self,
        driver,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
        nombre_tarjeta: str,
    ) -> list[MovimientoRaw]:
        """
        Extrae los movimientos del período en curso usando shadow DOM JS traversal.
        """
        movimientos: list[MovimientoRaw] = []

        try:
            rows = driver.execute_script(self._JS_EXTRACT_MOVEMENTS) or []
        except Exception as exc:
            log_fn(f"  JS_EXTRACT_MOVEMENTS error: {exc}")
            rows = []

        log_fn(f"  JS encontró {len(rows)} filas brutas")
        if rows:
            log_fn(f"  Primeras 5 filas: {rows[:5]}")

        for row in rows:
            mov = self._build_movimiento(row, fuente, usuario_default, nombre_tarjeta)
            if mov:
                movimientos.append(mov)

        if not movimientos and rows:
            log_fn("  Filas encontradas pero ninguna parseada — ver [diag] para ajustar")

        if not movimientos:
            log_fn("  ⚠ Sin movimientos — revisar [diag] del DOM de la tarjeta")

        return movimientos

    # ── Construcción de MovimientoRaw ─────────────────────────────────────────

    def _build_movimiento(
        self,
        row: dict,
        fuente: str,
        usuario_default: Optional[str],
        nombre_tarjeta: str,
    ) -> Optional[MovimientoRaw]:
        """
        Convierte un dict de fila cruda en un MovimientoRaw.

        Convención de monto (igual que todos los parsers CC de este proyecto):
          monto > 0 = egreso   (cargo en la tarjeta)
          monto < 0 = ingreso  (crédito / devolución)
        """
        fecha_str  = (row.get("fecha") or "").strip()
        desc       = (row.get("desc") or "").strip()
        amount_str = (row.get("amount") or "").strip()

        if not desc:
            return None

        # Parsear fecha — BBVA puede usar DD/MM/YYYY, DD-MMM-YY, YYYY-MM-DD o ISO
        fecha_iso = self._parse_fecha(fecha_str)
        if not fecha_iso:
            # Si no hay fecha parseable pero hay descripción e importe, omitimos el mov
            logger.debug("[bbva-tj] fecha no parseable: %r (desc=%r)", fecha_str, desc)
            return None

        # Parsear importe
        if not amount_str:
            return None
        monto = self.parse_amount(amount_str)
        if monto == 0.0:
            return None

        raw_data: dict = {"tarjeta": nombre_tarjeta}
        if usuario_default:
            raw_data["usuario"] = usuario_default
        if row.get("raw_text"):
            raw_data["raw_text"] = row["raw_text"][:200]

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha_iso,
            descripcion = desc[:200],
            monto       = monto,
            moneda      = "ARS",
            raw_data    = raw_data,
        )

    @staticmethod
    def _parse_fecha(text: str) -> Optional[str]:
        """
        Parsea la fecha de un movimiento BBVA.
        Formatos conocidos:
          DD/MM/YYYY  →  ISO
          DD-Mmm-YY   →  ISO  (ej. "21-May-26")
          YYYY-MM-DD  →  ISO  (ya está en formato correcto)
          DD/MM       →  no se puede determinar el año; usar año actual
        """
        if not text:
            return None
        text = text.strip()

        # ISO directo
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            return text

        # DD/MM/YYYY o DD-MM-YYYY
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", text)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            try:
                from datetime import date
                return date(year, month, day).isoformat()
            except ValueError:
                return None

        # DD-Mmm-YY (ej. "21-May-26")
        _MES = {
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
            "jan": 1, "apr": 4, "aug": 8, "dec": 12,
        }
        m2 = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$", text)
        if m2:
            day   = int(m2.group(1))
            mes   = _MES.get(m2.group(2).lower())
            year  = int(m2.group(3))
            if year < 100:
                year += 2000
            if mes:
                try:
                    from datetime import date
                    return date(year, mes, day).isoformat()
                except ValueError:
                    return None

        # DD/MM sin año — usar año actual como fallback
        m3 = re.match(r"^(\d{1,2})[/-](\d{1,2})$", text)
        if m3:
            from datetime import date
            day, month = int(m3.group(1)), int(m3.group(2))
            year = date.today().year
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None

        return None

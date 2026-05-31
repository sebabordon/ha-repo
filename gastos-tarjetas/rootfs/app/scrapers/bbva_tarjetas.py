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

    def _find_credit_cards(self, driver, log_fn) -> list[dict]:
        """
        Navega al dashboard de BBVA y busca las tarjetas de crédito visibles.

        Devuelve lista de dicts:
          {"tipo": "VISA"|"MC", "nombre": str, "url": str|None, "element": WebElement|None}

        Estrategia:
          1. Navegar a /fnetcore/ y esperar que Angular renderice los productos.
          2. Buscar elementos que mencionen "visa" o "mastercard" en el DOM.
          3. Intentar también las URLs canónicas de tarjeta para descubrir IDs.
        """
        from selenium.webdriver.common.by import By

        log_fn("Navegando al dashboard para encontrar tarjetas…")
        driver.get(f"{_BASE_URL}/fnetcore/")
        time.sleep(5)

        # Esperar a que Angular monte la posición global (hasta 20s)
        for _ in range(20):
            el = self.find(driver,
                "[id='@bbva/global-position'], "
                "[id='@bbva/cards'], "
                "bbva-web-global-position"
            )
            if el:
                break
            # También aceptar si ya hay contenido de productos en el DOM
            if self.find(driver, "[class*='product'], [class*='card-item'], bbva-product"):
                break
            time.sleep(1)

        # Pausa adicional para que los MFEs terminen de renderizar
        time.sleep(3)

        log_fn(f"URL tras carga dashboard: {(driver.current_url or '')[:150]}")

        # Volcar diagnóstico del DOM visible
        try:
            body_html = driver.execute_script(
                "return document.body.innerHTML.slice(0, 2000)"
            )
            log_fn(f"[diag] body[:2000]: {body_html}")
        except Exception:
            pass

        cards: list[dict] = []
        seen_urls: set[str] = set()

        # ── Estrategia A: buscar por texto de tarjeta en el DOM ───────────────
        # BBVA renderiza sus productos en web components; el texto del producto
        # (ej. "Visa Signature", "Mastercard Black") es accesible via innerText.
        card_selectors = [
            # Elementos con clases de producto / tarjeta de BBVA
            "[class*='product-item']",
            "[class*='card-product']",
            "[class*='tarjeta']",
            "bbva-product-card",
            "bbva-web-product-card",
            # Links que llevan al detalle de tarjeta
            "a[href*='tarjeta']",
            "a[href*='card']",
            # Cualquier elemento clicable con texto de Visa/MC
            "[role='listitem']",
            "[role='article']",
            "li",
        ]

        candidates = []
        for sel in card_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    log_fn(f"[diag] selector '{sel}': {len(els)} elementos")
                    candidates.extend(els)
            except Exception:
                pass

        for el in candidates:
            try:
                text = (el.text or "").strip()
                if not text:
                    # Intentar innerText vía JS
                    text = driver.execute_script(
                        "return arguments[0].innerText || ''", el
                    ) or ""
                if not text:
                    continue

                tipo = None
                if _VISA_RE.search(text):
                    tipo = "VISA"
                elif _MC_RE.search(text):
                    tipo = "MC"
                else:
                    continue

                # Obtener URL de destino
                href = el.get_attribute("href") or ""
                if not href:
                    # Buscar el primer <a> hijo
                    try:
                        a = el.find_element(By.TAG_NAME, "a")
                        href = a.get_attribute("href") or ""
                    except Exception:
                        pass

                # Normalizar nombre (primera línea del texto)
                nombre = text.split("\n")[0].strip()[:80]

                key = href or nombre
                if key in seen_urls:
                    continue
                seen_urls.add(key)

                cards.append({
                    "tipo":    tipo,
                    "nombre":  nombre,
                    "url":     href or None,
                    "element": el,
                })
                log_fn(f"  Encontrada: tipo={tipo} nombre={nombre!r} url={href[:80]}")
            except Exception as exc:
                logger.debug("[bbva-tj] error procesando candidato: %s", exc)

        # ── Estrategia B: URLs canónicas de tarjetas (si A no encontró nada) ──
        if not cards:
            log_fn("Estrategia A sin resultados — intentando URLs canónicas…")
            cards = self._discover_cards_by_url(driver, log_fn)

        return cards

    def _discover_cards_by_url(self, driver, log_fn) -> list[dict]:
        """
        Intenta navegar a URLs conocidas de tarjetas BBVA y confirma si carga.
        Fallback cuando la detección por DOM no funciona.
        """
        candidates = [
            # Rutas hash comunes del SPA de BBVA Argentina
            (f"{_BASE_URL}/fnetcore/#/tarjeta-credito/visa",        "VISA"),
            (f"{_BASE_URL}/fnetcore/#/tarjeta-credito/mastercard",  "MC"),
            (f"{_BASE_URL}/fnetcore/#/tarjetas/credito/visa",       "VISA"),
            (f"{_BASE_URL}/fnetcore/#/tarjetas/credito/mastercard", "MC"),
        ]
        cards = []
        for url, tipo in candidates:
            try:
                driver.get(url)
                time.sleep(3)
                cur = driver.current_url or ""
                # Si la URL se mantuvo y no volvimos al login → válida
                if "login" not in cur.lower() and url.split("#")[1] in cur:
                    nombre = "Tarjeta Visa" if tipo == "VISA" else "Tarjeta Mastercard"
                    cards.append({"tipo": tipo, "nombre": nombre, "url": url, "element": None})
                    log_fn(f"  URL canónica válida: {url}")
            except Exception as exc:
                log_fn(f"  URL {url} falló: {exc}")
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
        el     = card.get("element")

        # Navegar a la tarjeta
        if url:
            log_fn(f"  Navegando a {url[:100]}")
            driver.get(url)
        elif el:
            log_fn("  Haciendo click en el elemento de la tarjeta")
            try:
                self._click_element(driver, el)
            except Exception as exc:
                log_fn(f"  Click falló: {exc} — intentando JS click")
                driver.execute_script("arguments[0].click();", el)
        else:
            log_fn("  Sin URL ni elemento — saltando")
            return [], None

        # Esperar que el detalle de la tarjeta cargue
        time.sleep(3)
        for _ in range(15):
            # Buscar elementos típicos de la vista de movimientos
            if self.find(driver,
                "[class*='movement'], [class*='movimiento'], "
                "[class*='transaction'], [class*='transaccion'], "
                "bbva-web-movement-card, bbva-movement, "
                "table[class*='movement'], ul[class*='movement']"
            ):
                break
            time.sleep(1)

        log_fn(f"  URL detalle: {(driver.current_url or '')[:150]}")

        # Diagnóstico del DOM de la vista de tarjeta
        try:
            body_html = driver.execute_script(
                "return document.body.innerHTML.slice(0, 3000)"
            )
            log_fn(f"  [diag] body[:3000]: {body_html}")
        except Exception:
            pass

        saldo = self._extract_saldo(driver, log_fn)
        movimientos = self._extract_movimientos(driver, fuente, usuario_default, log_fn, nombre)
        return movimientos, saldo

    # ── Extracción de saldo ───────────────────────────────────────────────────

    def _extract_saldo(self, driver, log_fn) -> Optional[float]:
        """
        Intenta leer el saldo total a pagar de la tarjeta.
        Busca el importe destacado en la cabecera de detalle de la tarjeta.
        """
        selectors = [
            # Clases típicas de BBVA para el saldo principal
            "[class*='balance'] [class*='amount']",
            "[class*='balance']",
            "[class*='saldo']",
            "[class*='total-pagar']",
            "[class*='total']",
            # Web components de BBVA
            "bbva-web-amount",
            "bbva-amount",
        ]
        from selenium.webdriver.common.by import By
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    text = (el.text or "").strip()
                    if not text:
                        continue
                    # Buscar un importe monetario en el texto (tiene coma decimal)
                    m = re.search(r"[\d.]+,\d{2}", text.replace("\xa0", ""))
                    if m:
                        val = self.parse_amount(m.group(0))
                        if val > 0:
                            log_fn(f"  Saldo detectado: {text!r} → {val}")
                            return val
            except Exception:
                pass
        log_fn("  Saldo no detectado")
        return None

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
        Extrae todos los movimientos del período en curso de la vista actual.

        BBVA puede renderizarlos de varias formas según la versión del SPA:
          A. Lista de web components bbva-web-movement-card / bbva-movement
          B. Una <ul>/<ol> con <li> por movimiento
          C. Una <table> con filas de movimientos
          D. Divs con clases como 'movement-item', 'transaction-item', etc.

        Se intentan todas las estrategias y se devuelve la primera que
        produzca resultados. Con el log de diagnóstico el usuario puede
        calibrar los selectores exactos.
        """
        from selenium.webdriver.common.by import By

        movimientos: list[MovimientoRaw] = []

        # Cada estrategia devuelve lista de (fecha_str, desc, monto_str) o similar
        strategies = [
            self._parse_web_components,
            self._parse_list_items,
            self._parse_table_rows,
            self._parse_generic_divs,
        ]

        for strategy in strategies:
            try:
                rows = strategy(driver, log_fn)
                if rows:
                    log_fn(f"  Estrategia {strategy.__name__}: {len(rows)} filas")
                    for row in rows:
                        mov = self._build_movimiento(row, fuente, usuario_default, nombre_tarjeta)
                        if mov:
                            movimientos.append(mov)
                    if movimientos:
                        return movimientos
                    log_fn(f"  {strategy.__name__}: filas encontradas pero ninguna parseada")
            except Exception as exc:
                log_fn(f"  {strategy.__name__} error: {exc}")

        log_fn("  ⚠ Sin movimientos — revisar selectores (ver [diag] del DOM)")
        return []

    def _parse_web_components(self, driver, log_fn) -> list[dict]:
        """
        Parsea movimientos renderizados como web components de BBVA:
          <bbva-web-movement-card> o <bbva-movement>
        """
        from selenium.webdriver.common.by import By

        selectors = [
            "bbva-web-movement-card",
            "bbva-movement-card",
            "bbva-movement",
            "[is='bbva-movement']",
        ]
        rows = []
        for sel in selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if not els:
                continue
            log_fn(f"  WC selector '{sel}': {len(els)} elementos")
            for el in els:
                # Los web components de BBVA exponen sus datos como atributos
                fecha = (
                    el.get_attribute("date") or
                    el.get_attribute("transaction-date") or
                    el.get_attribute("fecha") or ""
                )
                desc = (
                    el.get_attribute("concept") or
                    el.get_attribute("description") or
                    el.get_attribute("descripcion") or
                    el.text or ""
                ).strip().split("\n")[0]
                amount = (
                    el.get_attribute("amount") or
                    el.get_attribute("monto") or
                    el.get_attribute("importe") or ""
                )
                if fecha or desc:
                    rows.append({"fecha": fecha, "desc": desc, "amount": amount, "raw_el": el})
            if rows:
                return rows
        return rows

    def _parse_list_items(self, driver, log_fn) -> list[dict]:
        """
        Parsea movimientos renderizados como <li> dentro de una lista de movimientos.
        Busca la lista más probable y extrae fecha/descripción/monto de cada ítem.
        """
        from selenium.webdriver.common.by import By

        list_selectors = [
            "[class*='movement-list'] li",
            "[class*='movimiento-list'] li",
            "[class*='transaction-list'] li",
            "ul[class*='movement'] li",
            "ul[class*='transaction'] li",
            "[class*='movements'] [class*='item']",
            "[class*='transactions'] [class*='item']",
        ]
        for sel in list_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if not els:
                continue
            log_fn(f"  LI selector '{sel}': {len(els)} elementos")
            rows = []
            for el in els:
                row = self._extract_row_data(driver, el)
                if row:
                    rows.append(row)
            if rows:
                return rows
        return []

    def _parse_table_rows(self, driver, log_fn) -> list[dict]:
        """
        Parsea movimientos en formato de tabla HTML (<table><tr>).
        """
        from selenium.webdriver.common.by import By

        table_selectors = [
            "table[class*='movement'] tr",
            "table[class*='transaction'] tr",
            "table tr",
        ]
        for sel in table_selectors:
            rows_els = driver.find_elements(By.CSS_SELECTOR, sel)
            if len(rows_els) < 2:
                continue
            log_fn(f"  TABLE selector '{sel}': {len(rows_els)} filas")
            rows = []
            for tr in rows_els:
                try:
                    cells = tr.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 2:
                        continue
                    texts = [c.text.strip() for c in cells]
                    # Heurística: primera celda con fecha, segunda con descripción,
                    # última con importe
                    fecha  = texts[0] if texts else ""
                    desc   = texts[1] if len(texts) > 1 else ""
                    amount = texts[-1] if len(texts) > 2 else ""
                    if fecha or desc:
                        rows.append({"fecha": fecha, "desc": desc, "amount": amount})
                except Exception:
                    pass
            if rows:
                return rows
        return []

    def _parse_generic_divs(self, driver, log_fn) -> list[dict]:
        """
        Parsea movimientos renderizados como divs con clases de movimiento.
        Última estrategia de fallback.
        """
        from selenium.webdriver.common.by import By

        div_selectors = [
            "[class*='movement-item']",
            "[class*='movimiento-item']",
            "[class*='transaction-item']",
            "[class*='TransactionItem']",
            "[class*='MovementItem']",
            "[class*='movement-row']",
            "[class*='transaction-row']",
        ]
        for sel in div_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if not els:
                continue
            log_fn(f"  DIV selector '{sel}': {len(els)} elementos")
            rows = []
            for el in els:
                row = self._extract_row_data(driver, el)
                if row:
                    rows.append(row)
            if rows:
                return rows
        return []

    def _extract_row_data(self, driver, el) -> Optional[dict]:
        """
        Extrae fecha, descripción e importe de un elemento de movimiento genérico.
        Busca sub-elementos con clases relacionadas o parsea el texto completo.
        """
        from selenium.webdriver.common.by import By
        try:
            text = (el.text or "").strip()
            if not text:
                return None

            # Intentar extraer sub-elementos con clases específicas
            fecha  = ""
            desc   = ""
            amount = ""

            for date_sel in ["[class*='date']", "[class*='fecha']", "time"]:
                try:
                    d = el.find_element(By.CSS_SELECTOR, date_sel)
                    fecha = (d.get_attribute("datetime") or d.text or "").strip()
                    if fecha:
                        break
                except Exception:
                    pass

            for desc_sel in ["[class*='concept']", "[class*='description']",
                             "[class*='descripcion']", "[class*='title']", "span", "p"]:
                try:
                    d = el.find_element(By.CSS_SELECTOR, desc_sel)
                    desc = (d.text or "").strip()
                    if desc and not re.match(r"^[\d,.$-]+$", desc):
                        break
                except Exception:
                    pass

            for amt_sel in ["[class*='amount']", "[class*='importe']",
                            "[class*='monto']", "[class*='price']"]:
                try:
                    d = el.find_element(By.CSS_SELECTOR, amt_sel)
                    amount = (d.text or "").strip()
                    if amount:
                        break
                except Exception:
                    pass

            # Si no encontramos sub-elementos, intentar parsear el texto completo
            if not fecha and not desc and not amount:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) >= 2:
                    fecha  = lines[0]
                    desc   = lines[1]
                    amount = lines[-1] if len(lines) > 2 else ""

            if not desc and not amount:
                return None

            return {"fecha": fecha, "desc": desc, "amount": amount, "raw_text": text}

        except Exception as exc:
            logger.debug("[bbva-tj] _extract_row_data error: %s", exc)
            return None

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

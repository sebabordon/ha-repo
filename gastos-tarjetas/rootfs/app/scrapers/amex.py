"""
Scraper AMEX Argentina — Selenium.

Flujo:
  1. Login en www.americanexpress.com/es-ar/account/login  (React SPA)
  2. Navegar al portal legacy global.americanexpress.com   (JSP server-side)
  3. Para cada producto de tarjeta (sorted_index 0 y 1):
       • Cargar la página de movimientos
       • Parsear secciones txnsCard0 / txnsCard1 / txnsCard2  (por cardholder)
       • Extraer fecha, descripción, monto, moneda

Estructura de la tabla de movimientos (ver samples/Amex Table.html):
  col 0 — fecha          <td id="{timestamp_ms}" class="inline_trans3">
  col 1 — descripción    <td class='desc'>
  col 2 — ARS pagos      <td class='amountPadding ar_bgroundcolor'>
  col 3 — ARS cargos     <td class='amountPadding'>
  col 4 — USD pagos      <td class='amountPadding ar_bgroundcolor'>
  col 5 — USD cargos     <td class='amountPadding'>

Filas en USD tienen la clase CSS adicional 'dollarText' en el <tr>.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.americanexpress.com/es-ar/account/login"

_LOGIN_POST_URL = (
    "https://global.americanexpress.com/myca/logon/canlac/action/login"
)

_ACCOUNT_SUMMARY = (
    "https://global.americanexpress.com/myca/intl/acctsumm/canlac/"
    "accountSummary.do?request_type=&Face=es_AR"
)

_STATEMENTS_PAGE = "https://global.americanexpress.com/statements"

_STATEMENT_URL = (
    "https://global.americanexpress.com/myca/intl/estatement/canlac/"
    "statement.do?request_type=&Face=es_AR&BPIndex=0&sorted_index={idx}"
)

# sorted_index → código interno de tarjeta (almacenado en movimientos_raw.tarjeta)
_CARD_PRODUCTS = [
    {"idx": "0", "tarjeta": "platinum_card",   "nombre": "The Platinum Card"},
    {"idx": "1", "tarjeta": "platinum_credit", "nombre": "The Platinum Credit Card"},
]

# Non-breaking space que Selenium devuelve cuando el HTML tiene &nbsp;
_NBSP = "\xa0"

# Detecta el número de cuota en la descripción: "3/12", "01/6", "03/24", etc.
_CUOTA_RE = re.compile(r"\b(\d{1,2}/\d{1,3})\b")


class AmexScraper(BaseScraper):
    fuente       = "amex"
    nombre       = "AMEX Argentina"
    login_origin = "https://www.americanexpress.com"

    # ── Verificación de sesión ────────────────────────────────────────────────

    def check_session(self, driver) -> bool:
        """
        Navega al portal legacy. Si hay sesión activa llega a la página de
        account summary (div#middleContentHeader). Si no, redirige al login.
        """
        try:
            logger.info("[amex] check_session: navegando al portal legacy")
            driver.get(_ACCOUNT_SUMMARY)
            time.sleep(3)
            current_url = driver.current_url
            logger.info("[amex] check_session: URL tras navegación = %s", current_url[:100])
            el = self.find(
                driver,
                "div#middleContentHeader, div#summaryWrap, "
                "select#cardAccount, div#leftNav",
            )
            logger.info(
                "[amex] check_session: elemento portal encontrado = %s%s",
                el is not None,
                f" (title={driver.title[:60]!r})" if not el else "",
            )
            return el is not None
        except Exception as exc:
            logger.debug("[amex] check_session error: %s", exc)
            return False

    # ── Login ─────────────────────────────────────────────────────────────────

    # ── Helpers robustos de interacción ───────────────────────────────────────

    @staticmethod
    def _find_visible(driver, css_selector: str):
        """Devuelve el primer elemento visible+habilitado que matchea, o None."""
        from selenium.webdriver.common.by import By
        for el in driver.find_elements(By.CSS_SELECTOR, css_selector):
            try:
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception:
                pass
        return None

    @staticmethod
    def _type_into(driver, el, value: str) -> None:
        """
        Escribe en un input con scroll-into-view previo y fallback JS si Selenium
        lo reporta no interactuable (setea value + dispara input/change para que
        un SPA registre el cambio).
        """
        from selenium.common.exceptions import (
            ElementNotInteractableException,
            InvalidElementStateException,
        )
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        try:
            el.clear()
            el.send_keys(value)
        except (ElementNotInteractableException, InvalidElementStateException):
            driver.execute_script(
                "arguments[0].value=arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                el, value,
            )

    @staticmethod
    def _click_el(driver, el) -> None:
        """Click con scroll-into-view previo y fallback a click vía JS."""
        from selenium.common.exceptions import (
            ElementNotInteractableException,
            ElementClickInterceptedException,
        )
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        try:
            el.click()
        except (ElementNotInteractableException, ElementClickInterceptedException):
            driver.execute_script("arguments[0].click();", el)

    @staticmethod
    def _react_set_input(driver, element_id: str, value: str) -> None:
        """Escribe en un input controlado por React usando el setter nativo."""
        driver.execute_script("""
            var el = document.getElementById(arguments[0]);
            if (!el) return;
            el.focus();
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(el, arguments[1]);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, element_id, value)

    def _login_diag(self, driver) -> str:
        """Captura diagnóstico del estado del browser para errores de login."""
        from selenium.webdriver.common.by import By
        parts = [
            f"URL: {driver.current_url[:120]}",
            f"Título: {driver.title[:80]!r}",
        ]
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            for inp in inputs[:10]:
                attrs = {a: inp.get_attribute(a) for a in ("id", "name", "type", "autocomplete") if inp.get_attribute(a)}
                vis = "visible" if inp.is_displayed() else "oculto"
                parts.append(f"  <input {attrs}> [{vis}]")
            btns = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in btns[:6]:
                bid = btn.get_attribute("id") or ""
                btype = btn.get_attribute("type") or ""
                btxt = (btn.text or "")[:30]
                vis = "visible" if btn.is_displayed() else "oculto"
                parts.append(f"  <button id={bid!r} type={btype!r}> {btxt!r} [{vis}]")
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                parts.append(f"  iframes: {len(iframes)}")
        except Exception as exc:
            parts.append(f"  (error capturando DOM: {exc})")
        return "\n".join(parts)

    def do_login(self, driver, config: dict) -> None:
        """
        Login en AMEX AR via POST directo al endpoint de login.

        InAuth (device fingerprinting de AMEX) bloquea el submit del form React
        en Chromium headless. Se bypasea haciendo el POST directamente con
        fetch(), que es la misma request que el form haría si InAuth lo dejara.
        """
        from selenium.common.exceptions import TimeoutException

        logger.info("[amex] do_login: navegando a %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)

        # Esperar a que la página cargue (establece cookies necesarias)
        try:
            self.wait_visible(driver, "input#eliloUserID", timeout=20)
        except TimeoutException:
            diag = self._login_diag(driver)
            raise TimeoutException(f"Página de login no cargó.\n{diag}")

        # Dar tiempo a que los scripts se inicialicen (cookies de sesión, etc.)
        time.sleep(3)

        # ── POST directo al endpoint de login ─────────────────────────────────
        logger.info("[amex] do_login: haciendo POST directo al endpoint de login")
        driver.set_script_timeout(30)
        login_result = driver.execute_async_script("""
            var userId   = arguments[0];
            var password = arguments[1];
            var cb       = arguments[arguments.length - 1];

            var params = new URLSearchParams();
            params.set('request_type', 'login');
            params.set('Face', 'es_AR');
            params.set('Logon', 'Logon');
            params.set('version', '4');
            params.set('DestPage', 'https://global.americanexpress.com/dashboard');
            params.set('UserID', userId);
            params.set('Password', password);
            params.set('channel', 'Web');
            params.set('REMEMBERME', 'off');

            var now = new Date();
            params.set('b_hour',      String(now.getHours()));
            params.set('b_minute',    String(now.getMinutes()));
            params.set('b_second',    String(now.getSeconds()));
            params.set('b_dayNumber', String(now.getDate()));
            params.set('b_month',     String(now.getMonth() + 1));
            params.set('b_year',      String(now.getFullYear()));
            params.set('b_timeZone',  String(-now.getTimezoneOffset() / 60));

            fetch(arguments[2], {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
                    'Origin': 'https://www.americanexpress.com'
                },
                body: params.toString()
            })
            .then(function(r) {
                return r.text().then(function(t) {
                    cb({status: r.status, body: t.substring(0, 500), ok: r.ok});
                });
            })
            .catch(function(e) { cb({status: 0, error: String(e)}); });
        """, config["usuario"], config["password"], _LOGIN_POST_URL) or {}

        status = login_result.get("status", 0)
        logger.info(
            "[amex] do_login: POST login status=%s, body=%s",
            status, str(login_result.get("body", ""))[:200],
        )

        if login_result.get("error"):
            raise RuntimeError(
                f"Login POST falló: {login_result['error']}"
            )
        if status not in (200, 201, 302):
            raise RuntimeError(
                f"Login POST status {status}: {str(login_result.get('body', ''))[:300]}"
            )

        # ── Navegar al portal ─────────────────────────────────────────────────
        logger.info("[amex] do_login: login POST OK, navegando al portal")
        driver.get(_ACCOUNT_SUMMARY)

        _portal_sel = (
            "div#middleContentHeader, div#leftNav, select#cardAccount, "
            "div[data-module-name='axp-account-summary'], "
            "[data-testid='account-summary']"
        )
        try:
            self.wait_for(driver, _portal_sel, timeout=30)
        except TimeoutException:
            diag = self._login_diag(driver)
            raise TimeoutException(
                f"Portal post-login no cargó tras 30s (login POST fue {status}).\n{diag}"
            )
        logger.info("[amex] do_login: portal cargado, URL = %s", driver.current_url[:100])
        logger.info("[amex] Login exitoso")

    # ── Scrape principal ──────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        movimientos: list[MovimientoRaw] = []
        saldo_ars_total = 0.0
        saldo_usd_total = 0.0
        log_lines: list[str] = []

        for producto in _CARD_PRODUCTS:
            url = _STATEMENT_URL.format(idx=producto["idx"])
            try:
                movs, s_ars, s_usd = self._scrape_producto(
                    driver, url, producto["tarjeta"], producto["nombre"], log_lines
                )
                movimientos.extend(movs)
                saldo_ars_total += s_ars
                saldo_usd_total += s_usd
            except Exception as exc:
                msg = f"Error scrapeando '{producto['nombre']}': {exc}"
                logger.error("[amex] %s", msg, exc_info=True)
                log_lines.append(f"✗ {msg}")

        if config.get("auto_resumenes"):
            try:
                self._scrape_resumenes(driver, config, log_lines.append)
            except Exception as exc:
                logger.error("[amex] _scrape_resumenes: %s", exc, exc_info=True)
                log_lines.append(f"✗ Error descargando resúmenes: {exc}")

        saldos: dict = {}
        if saldo_ars_total or saldo_usd_total:
            saldos["amex"] = {}
            if saldo_ars_total:
                saldos["amex"]["saldo_ars"] = saldo_ars_total
            if saldo_usd_total:
                saldos["amex"]["saldo_usd"] = saldo_usd_total

        return ScraperResult(fuente="amex", movimientos=movimientos, saldos=saldos, log_lines=log_lines)

    # ── Scrape de un producto de tarjeta ──────────────────────────────────────

    def _scrape_producto(
        self,
        driver,
        url: str,
        tarjeta: str,
        nombre: str,
        log: list | None = None,
    ) -> tuple[list[MovimientoRaw], float, float]:
        """
        Carga la página de movimientos para un sorted_index y parsea todas las
        secciones txnsCard.

        Devuelve (movimientos, saldo_ars, saldo_usd).
        log es una lista compartida donde se acumulan líneas de diagnóstico.
        """
        from selenium.webdriver.common.by import By

        if log is None:
            log = []

        def _l(msg: str) -> None:
            logger.info("[amex] %s", msg)
            log.append(msg)

        _l(f"[{nombre}] Navegando a statement URL (sorted_index={url[-1:]})")
        driver.get(url)

        # Esperar que cargue la sección de transacciones
        try:
            self.wait_for(driver, "div#txnsSection, div#statementWrap", timeout=25)
            _l(f"[{nombre}] URL cargada: {driver.current_url[:100]}")
        except Exception as exc:
            _l(f"[{nombre}] ⚠ Timeout esperando div#txnsSection / div#statementWrap: {exc}")
            _l(f"[{nombre}] URL actual: {driver.current_url[:100]}")
            _l(f"[{nombre}] Título de página: {driver.title[:80]!r}")
            return [], 0.0, 0.0

        time.sleep(1)   # breve pausa para que JS termine de actualizar el DOM

        movimientos: list[MovimientoRaw] = []

        # ── Saldo actual ──────────────────────────────────────────────────────
        saldo_ars = 0.0
        saldo_usd = 0.0
        try:
            saldo_el = self.find(driver, "td#colOSBalance")
            if saldo_el:
                raw_saldo = saldo_el.text.strip()
                _l(f"[{nombre}] Texto saldo: {raw_saldo!r}")
                for line in raw_saldo.split("\n"):
                    line = line.strip()
                    # USD primero (U$S) para no confundir con el '$' de ARS
                    if "U$S" in line or "U$" in line:
                        saldo_usd = abs(self._parse_usd_amount(line))
                    elif "$" in line:
                        # Handles both '$2.932.743,58' and '-$132,70'
                        saldo_ars = abs(self.parse_amount(line))
            else:
                _l(f"[{nombre}] ⚠ No se encontró td#colOSBalance (saldo)")
        except Exception as exc:
            _l(f"[{nombre}] ⚠ Error leyendo saldo: {exc}")

        _l(f"[{nombre}] Saldo ARS={saldo_ars:.2f} USD={saldo_usd:.2f}")

        # ── Nombres de cardholders desde el selector ──────────────────────────
        cardholder_map: dict[str, str] = {}
        try:
            opts = driver.find_elements(By.CSS_SELECTOR, "#cardAccount option")
            _l(f"[{nombre}] Opciones en #cardAccount: {len(opts)}")
            for opt in opts:
                val = opt.get_attribute("value") or ""
                if val not in ("", "all"):
                    cardholder_map[val] = opt.text.strip()
            _l(f"[{nombre}] Cardholders: {cardholder_map}")
        except Exception as exc:
            _l(f"[{nombre}] ⚠ Error leyendo cardholders: {exc}")

        # ── Parseo desde el HTML CRUDO del servidor (vía primaria) ────────────
        # El JS de AMEX colapsa las secciones txnsCard0/1/2 (una por titular) en
        # una lista plana tras cargar, así que el DOM en vivo pierde la separación
        # por titular en el período abierto. El HTML CRUDO del servidor sí trae
        # esas secciones: se lo trae con un XHR same-origin y se parsea con el
        # DOMParser del browser (que NO ejecuta scripts → las secciones quedan
        # intactas). Funciona igual para resumen abierto y cerrado.
        raw_movs = self._scrape_raw_txns(driver, url, tarjeta, cardholder_map, nombre, _l)
        if raw_movs:
            movimientos.extend(raw_movs)
            _l(f"[{nombre}] Total movimientos: {len(movimientos)}")
            return movimientos, saldo_ars, saldo_usd

        # ── Fallback: DOM en vivo (si el XHR falla o cambia la estructura) ─────
        card_divs = driver.find_elements(By.CSS_SELECTOR, "div[id^='txnsCard']")
        _l(f"[{nombre}] Secciones div[id^='txnsCard'] encontradas: {len(card_divs)}")

        if card_divs:
            # Vista de estado de cuenta cerrado — hay un div por cardholder
            for card_div in card_divs:
                div_id     = card_div.get_attribute("id") or ""
                card_idx   = div_id.replace("txnsCard", "")
                cardholder = cardholder_map.get(card_idx, f"card_{card_idx}")

                rows = card_div.find_elements(
                    By.CSS_SELECTOR, "tr.tableStandardText.pagebreak"
                )
                _l(f"[{nombre}] {div_id} (cardholder={cardholder!r}): {len(rows)} filas")
                parsed_ok = 0
                for row in rows:
                    mov = self._parse_row(row, tarjeta, cardholder)
                    if mov:
                        movimientos.append(mov)
                        parsed_ok += 1
                _l(f"[{nombre}] {div_id}: {parsed_ok}/{len(rows)} filas parseadas")
        else:
            # Vista "Últimos Movimientos" (período abierto) — filas directamente
            # bajo div#txnsSection sin el wrapper txnsCard por cardholder.
            txns_section = self.find(driver, "div#txnsSection")
            _l(f"[{nombre}] Fallback: div#txnsSection presente = {txns_section is not None}")
            if txns_section:
                rows = txns_section.find_elements(
                    By.CSS_SELECTOR, "tr.tableStandardText.pagebreak"
                )
                _l(f"[{nombre}] Fallback: {len(rows)} filas en div#txnsSection")
                # En el período abierto la página NO separa por titular: el
                # selector #cardAccount solo togglea client-side las secciones
                # txnsCard, que en esta vista no existen (confirmado en vivo:
                # filtrar por cada titular deja las MISMAS 17 filas). Por eso solo
                # es seguro asignar titular cuando hay UN único titular; con
                # varios se deja vacío y el import resuelve por el default de la
                # fuente. La atribución por titular se obtiene del resumen CERRADO
                # (secciones txnsCard, ver rama de arriba).
                default_ch = (
                    next(iter(cardholder_map.values())) if len(cardholder_map) == 1 else ""
                )
                if not default_ch and len(cardholder_map) > 1:
                    _l(f"[{nombre}] Fallback: {len(cardholder_map)} titulares — "
                       f"período abierto no separa por titular; cardholder vacío")
                parsed_ok = 0
                for row in rows:
                    mov = self._parse_row(row, tarjeta, default_ch)
                    if mov:
                        movimientos.append(mov)
                        parsed_ok += 1
                _l(f"[{nombre}] Fallback: {parsed_ok}/{len(rows)} filas parseadas")
            else:
                all_divs = driver.find_elements(By.CSS_SELECTOR, "div[id]")
                txns_ids = [
                    d.get_attribute("id") for d in all_divs
                    if (d.get_attribute("id") or "").startswith("txns")
                ]
                _l(f"[{nombre}] ⚠ Sin txnsSection. IDs con prefijo 'txns': {txns_ids[:10]}")

        _l(f"[{nombre}] Total movimientos: {len(movimientos)}")
        return movimientos, saldo_ars, saldo_usd

    # ── Parseo desde el HTML crudo del servidor ───────────────────────────────

    def _scrape_raw_txns(
        self,
        driver,
        url: str,
        tarjeta: str,
        cardholder_map: dict,
        nombre: str,
        _l,
    ) -> list[MovimientoRaw]:
        """
        Trae el HTML crudo de `url` con un XHR síncrono same-origin y lo parsea
        con el DOMParser del browser (que no ejecuta scripts). Extrae las filas
        de cada sección div#txnsCardN — una por titular — que el JS de la página
        colapsa en el DOM en vivo. Devuelve [] si no encuentra secciones (ahí el
        caller usa el fallback sobre el DOM en vivo).
        """
        js = r"""
        var url = arguments[0];
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', url, false);
            xhr.send(null);
            if (xhr.status !== 200) return {error: 'status ' + xhr.status};
            var doc = new DOMParser().parseFromString(xhr.responseText, 'text/html');
            var out = [];
            doc.querySelectorAll("div[id^='txnsCard']").forEach(function (div) {
                var idx = div.id.replace('txnsCard', '');
                div.querySelectorAll("tr.tableStandardText.pagebreak").forEach(function (tr) {
                    var td = tr.querySelectorAll('td');
                    if (td.length < 6) return;
                    out.push({
                        card:      idx,
                        dateText:  (td[0].textContent || '').trim(),
                        dateId:    td[0].id || '',
                        desc:      (td[1].textContent || '').trim(),
                        arsPago:   (td[2].textContent || '').trim(),
                        arsCargo:  (td[3].textContent || '').trim(),
                        usdPago:   (td[4].textContent || '').trim(),
                        usdCargo:  (td[5].textContent || '').trim(),
                        isDollar:  (tr.className || '').indexOf('dollarText') >= 0
                    });
                });
            });
            return {rows: out};
        } catch (e) {
            return {error: String(e)};
        }
        """
        try:
            res = driver.execute_script(js, url) or {}
        except Exception as exc:
            _l(f"[{nombre}] HTML crudo: error ejecutando XHR/DOMParser: {exc}")
            return []

        if res.get("error"):
            _l(f"[{nombre}] HTML crudo: {res['error']} — uso fallback DOM en vivo")
            return []

        rows = res.get("rows") or []
        if not rows:
            _l(f"[{nombre}] HTML crudo: 0 secciones txnsCard — uso fallback DOM en vivo")
            return []

        movimientos: list[MovimientoRaw] = []
        por_titular: dict[str, int] = {}
        for r in rows:
            cardholder = cardholder_map.get(r.get("card", ""), "")
            mov = self._row_from_raw(r, tarjeta, cardholder)
            if mov:
                movimientos.append(mov)
                por_titular[cardholder or "(sin titular)"] = (
                    por_titular.get(cardholder or "(sin titular)", 0) + 1
                )
        _l(f"[{nombre}] HTML crudo: {len(movimientos)} movimientos por titular: {por_titular}")
        return movimientos

    def _row_from_raw(
        self, r: dict, tarjeta: str, cardholder: str
    ) -> MovimientoRaw | None:
        """Convierte un dict de fila cruda (del DOMParser) en MovimientoRaw."""
        try:
            # ── Fecha ─────────────────────────────────────────────────────────
            fecha_text = (r.get("dateText") or "").strip()
            if fecha_text:
                fecha_iso = self.parse_date_ar(fecha_text)
            else:
                ts_attr = (r.get("dateId") or "").strip()
                if ts_attr.isdigit():
                    dt = datetime.fromtimestamp(int(ts_attr) / 1000, tz=timezone.utc)
                    fecha_iso = dt.strftime("%Y-%m-%d")
                else:
                    return None
            if not fecha_iso:
                return None

            # ── Descripción ───────────────────────────────────────────────────
            desc = (r.get("desc") or "").replace(_NBSP, " ").strip()
            if not desc:
                return None

            # ── Moneda y monto ────────────────────────────────────────────────
            if r.get("isDollar"):
                txt_pago  = _clean(r.get("usdPago", ""))
                txt_cargo = _clean(r.get("usdCargo", ""))
                if txt_cargo:
                    monto =  abs(self._parse_usd_amount(txt_cargo))
                elif txt_pago:
                    monto = -abs(self._parse_usd_amount(txt_pago))
                else:
                    return None
                moneda = "USD"
            else:
                txt_pago  = _clean(r.get("arsPago", ""))
                txt_cargo = _clean(r.get("arsCargo", ""))
                if txt_cargo:
                    monto =  abs(self.parse_amount(txt_cargo))
                elif txt_pago:
                    monto = -abs(self.parse_amount(txt_pago))
                else:
                    return None
                moneda = "ARS"

            raw_data: dict = {"cardholder": cardholder}
            cuota_m = _CUOTA_RE.search(desc)
            if cuota_m:
                raw_data["cuota"] = cuota_m.group(1)

            return MovimientoRaw(
                fuente      = "amex",
                fecha       = fecha_iso,
                descripcion = desc,
                monto       = monto,
                moneda      = moneda,
                tarjeta     = tarjeta,
                raw_data    = raw_data,
            )
        except Exception as exc:
            logger.warning("[amex] Error parseando fila cruda: %s", exc)
            return None

    # ── Parseo de fila de transacción ─────────────────────────────────────────

    def _parse_row(
        self, row, tarjeta: str, cardholder: str
    ) -> MovimientoRaw | None:
        """
        Parsea una fila <tr class='tableStandardText pagebreak'>.

        Columnas (0-indexed):
          0 → fecha      (texto DD-MM-YYYY, o id = timestamp en ms)
          1 → descripción
          2 → ARS pago   (crédito → monto negativo)
          3 → ARS cargo  (egreso → monto positivo)
          4 → USD pago   (crédito → monto negativo)
          5 → USD cargo  (egreso → monto positivo)

        Las filas USD llevan la clase CSS 'dollarText' en el <tr>.
        """
        from selenium.webdriver.common.by import By

        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 6:
                return None

            # ── Fecha ─────────────────────────────────────────────────────────
            fecha_text = cells[0].text.strip()
            if fecha_text:
                fecha_iso = self.parse_date_ar(fecha_text)
            else:
                # Fallback: el atributo id de la celda es un timestamp en ms
                ts_attr = cells[0].get_attribute("id") or ""
                if ts_attr.isdigit():
                    dt = datetime.fromtimestamp(int(ts_attr) / 1000, tz=timezone.utc)
                    fecha_iso = dt.strftime("%Y-%m-%d")
                else:
                    return None
            if not fecha_iso:
                return None

            # ── Descripción ───────────────────────────────────────────────────
            desc = cells[1].text.strip().replace(_NBSP, " ").strip()
            if not desc:
                return None

            # ── Moneda y monto ────────────────────────────────────────────────
            is_dollar = "dollarText" in (row.get_attribute("class") or "")

            if is_dollar:
                txt_pago  = _clean(cells[4].text)
                txt_cargo = _clean(cells[5].text)
                if txt_cargo:
                    monto  =  abs(self._parse_usd_amount(txt_cargo))   # egreso
                elif txt_pago:
                    monto  = -abs(self._parse_usd_amount(txt_pago))    # crédito
                else:
                    return None
                moneda = "USD"
            else:
                txt_pago  = _clean(cells[2].text)
                txt_cargo = _clean(cells[3].text)
                if txt_cargo:
                    monto  =  abs(self.parse_amount(txt_cargo))        # egreso
                elif txt_pago:
                    monto  = -abs(self.parse_amount(txt_pago))         # crédito
                else:
                    return None
                moneda = "ARS"

            raw_data: dict = {"cardholder": cardholder}
            cuota_m = _CUOTA_RE.search(desc)
            if cuota_m:
                raw_data["cuota"] = cuota_m.group(1)   # e.g. "3/12"

            return MovimientoRaw(
                fuente      = "amex",
                fecha       = fecha_iso,
                descripcion = desc,
                monto       = monto,
                moneda      = moneda,
                tarjeta     = tarjeta,
                raw_data    = raw_data,
            )

        except Exception as exc:
            logger.warning("[amex] Error parseando fila: %s", exc)
            return None

    # ── Auto-descarga de resúmenes PDF ────────────────────────────────────────

    def _scrape_resumenes(self, driver, config: dict, log_fn) -> None:
        """
        Descarga e importa el resumen PDF más reciente de AMEX.

        Estrategia: navegar a /statements (One App SPA), esperar que renderice,
        y extraer los links de descarga directamente del DOM. Las URLs están en
        <a href="/servicing/v1/documents/statements/{TOKEN}?account_key=...">
        sin necesidad de llamadas a API ni tokens adicionales.
        """
        from db import importacion_exists

        log_fn("Buscando resúmenes PDF AMEX…")

        account_key = (config.get("statements_account_key") or "").strip()
        statements_url = (
            f"{_STATEMENTS_PAGE}?account_key={account_key}"
            if account_key
            else _STATEMENTS_PAGE
        )
        try:
            driver.get(statements_url)
        except Exception as exc:
            log_fn(f"  [amex-pdf] error navegando a /statements: {exc}")
            return

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        # Esperar a que el SPA renderice los botones del acordeón (hasta 30s)
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[id^="header-"]'))
            )
            time.sleep(1)
        except Exception:
            log_fn(f"  [amex-pdf] timeout esperando panel de resúmenes (URL={driver.current_url[:80]})")
            return

        # Los resúmenes están agrupados en acordeones por período (ej. "2026" y
        # "mar.-dic. 2025"), cada uno carga sus links lazy al expandirse. Expandimos
        # los paneles cuyo año alcance la ventana pedida y, tras cada expansión,
        # extraemos sus links y los acumulamos: algunos acordeones colapsan el panel
        # anterior al abrir otro, así que no confiamos en tenerlos todos abiertos a la vez.
        import re as _re
        cutoff_year = self._resumenes_cutoff(config).year

        # JS: extrae los links de descarga del DOM. La fecha se parsea del title
        # ("... - 26 de may de 2026"); el mes se normaliza a 3 letras porque AMEX usa
        # "sept" además de "sep". El selector se hace por indexOf (no [href*=]) porque
        # el CSS no matchea bien en esta SPA de React.
        _links_js = """
        return (function() {
            var MONTHS = {
                'ene':'01','feb':'02','mar':'03','abr':'04','may':'05','jun':'06',
                'jul':'07','ago':'08','sep':'09','oct':'10','nov':'11','dic':'12'
            };
            function titleToDate(title) {
                var m = /(\\d+) de (\\w+) de (\\d{4})/.exec(title || '');
                if (!m) return '';
                var mon = MONTHS[m[2].toLowerCase().slice(0, 3)];
                if (!mon) return '';
                return m[3] + '-' + mon + '-' + ('0' + m[1]).slice(-2);
            }
            var out = [];
            var all = document.querySelectorAll('a[href]');
            for (var i = 0; i < all.length; i++) {
                var a = all[i];
                var attr = a.getAttribute('href') || a.href || '';
                if (attr.indexOf('/servicing/v1/documents/statements/') < 0) continue;
                var url = a.href || attr;
                out.push({url: url, date: titleToDate(a.title), title: a.title || ''});
            }
            return out;
        })();
        """
        _wait_links_js = """
            var all = document.querySelectorAll('a[href]');
            for (var i = 0; i < all.length; i++) {
                var h = all[i].getAttribute('href') || all[i].href || '';
                if (h.indexOf('/servicing/v1/documents/statements/') >= 0) return true;
            }
            return false;
        """

        links_by_url = {}

        def _collect_links():
            for it in (driver.execute_script(_links_js) or []):
                u = it.get("url")
                if u and u not in links_by_url:
                    links_by_url[u] = it

        try:
            btns = driver.find_elements(By.CSS_SELECTOR, 'button[id^="header-"]')
            log_fn(f"  [amex-pdf] {len(btns)} panel(es) de resúmenes (desde año {cutoff_year})")
            for b in btns:
                try:
                    bid = b.get_attribute("id") or ""
                    ym  = _re.search(r"(\d{4})", bid)
                    if ym and int(ym.group(1)) < cutoff_year:
                        continue  # panel de un año anterior a la ventana
                    if (b.get_attribute("aria-expanded") or "") == "false":
                        log_fn(f"  [amex-pdf] expandiendo panel {bid or '(sin id)'}…")
                        driver.execute_script("arguments[0].click();", b)
                        time.sleep(0.6)
                    try:
                        WebDriverWait(driver, 45).until(lambda d: d.execute_script(_wait_links_js))
                    except Exception:
                        pass  # el diagnóstico más abajo mostrará qué hay en el DOM
                    time.sleep(0.3)
                    _collect_links()
                except Exception:
                    continue
        except Exception as exc:
            log_fn(f"  [amex-pdf] aviso expandiendo paneles: {exc}")

        links = list(links_by_url.values())

        if not links:
            # Diagnóstico: mostrar qué hrefs existen para entender el formato real
            try:
                diag = driver.execute_script("""
                var all = document.querySelectorAll('a[href]');
                var sample = [];
                for (var i = 0; i < all.length; i++) {
                    var h = all[i].getAttribute('href') || '';
                    if (h.indexOf('document') >= 0 || h.indexOf('statement') >= 0
                            || h.indexOf('pdf') >= 0 || h.indexOf('servicing') >= 0) {
                        sample.push(h.substring(0, 100));
                        if (sample.length >= 5) break;
                    }
                }
                return {
                    total_a: all.length,
                    sample: sample,
                    has_stmts: document.body.innerText.indexOf('Estado') >= 0,
                    url: location.href
                };
                """) or {}
                log_fn(
                    f"  [amex-pdf] sin links de resúmenes — "
                    f"<a href> en página: {diag.get('total_a',0)}, "
                    f"texto 'Estado' presente: {diag.get('has_stmts')}, "
                    f"URL: {str(diag.get('url',''))[:80]}"
                )
                for h in (diag.get("sample") or []):
                    log_fn(f"  [amex-pdf]   href candidato: {h}")
                if not (diag.get("sample")):
                    log_fn("  [amex-pdf]   (ningún href con 'document'/'statement'/'pdf'/'servicing')")
            except Exception:
                log_fn(f"  [amex-pdf] sin links de resúmenes en la página (URL={driver.current_url[:80]})")
            return

        log_fn(f"  [amex-pdf] {len(links)} resúmenes encontrados en la página")

        # Backfill: importar los resúmenes con fecha de cierre dentro de la ventana
        # configurada ('resumenes_meses', default 1 = solo el último mes). Los ya
        # importados se saltean. Los links vienen del más reciente al más antiguo.
        from datetime import date as _date
        cutoff = self._resumenes_cutoff(config)
        log_fn(f"  [amex-pdf] importando resúmenes desde {cutoff.isoformat()}…")
        importados = 0
        for link in links:
            url  = link.get("url", "")
            date = link.get("date", "")   # "YYYY-MM-DD"
            if not url:
                continue

            # Filtrar por ventana. Si no hay fecha parseable, NO lo importamos: no
            # podemos ubicarlo en la ventana y arriesgaríamos traer un resumen viejo
            # (ej. título "30 de sept de 2025" que no se pudo parsear).
            d = None
            if date:
                try:
                    d = _date.fromisoformat(date)
                except ValueError:
                    d = None
            if d is None:
                log_fn(f"  [amex-pdf] salteado (sin fecha parseable): {link.get('title', '')[:50]}")
                continue
            if d < cutoff:
                continue

            filename = f"AMEX_{date}_auto.pdf"
            if importacion_exists("amex", filename):
                log_fn(f"  [amex-pdf] al día ({date or link.get('title', '')})")
                continue

            log_fn(f"  [amex-pdf] descargando {date or link.get('title', '')}…")
            pdf_bytes = self._fetch_amex_pdf(driver, url, log_fn)
            if not pdf_bytes:
                continue  # error de descarga puntual, seguir con el resto
            count = self._import_resumen_amex(pdf_bytes, filename, log_fn)
            log_fn(f"  [amex-pdf] {filename}: {count} gastos importados")
            if count > 0:
                importados += 1

        if importados:
            log_fn(f"  [amex-pdf] {importados} resumen(es) nuevos importados")

    def _fetch_amex_pdf(self, driver, url: str, log_fn) -> Optional[bytes]:
        """
        Descarga el PDF de un resumen usando la URL completa del link del DOM.
        El browser ya tiene la sesión activa; credentials:'include' envía las cookies.
        """
        import base64 as _b64

        js = """
        var url = arguments[0];
        var cb  = arguments[arguments.length - 1];
        fetch(url, {method: 'GET', credentials: 'include'})
        .then(function(r) {
            return r.arrayBuffer().then(function(buf) {
                if (!buf || buf.byteLength === 0) {
                    cb({status: r.status, base64: '', error: 'empty'});
                    return;
                }
                var bytes = new Uint8Array(buf);
                var str = '';
                var CHUNK = 8192;
                for (var i = 0; i < bytes.length; i += CHUNK)
                    str += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
                cb({status: r.status, base64: btoa(str)});
            });
        })
        .catch(function(e) { cb({status: 0, base64: '', error: String(e)}); });
        """
        try:
            driver.set_script_timeout(60)
            result = driver.execute_async_script(js, url) or {}
        except Exception as exc:
            log_fn(f"  [amex-pdf] error descargando PDF: {exc}")
            return None

        if result.get("error") or result.get("status") not in (200, 201):
            log_fn(f"  [amex-pdf] PDF HTTP {result.get('status')} — {str(result.get('error',''))[:100]}")
            return None

        b64 = result.get("base64") or ""
        if not b64:
            log_fn("  [amex-pdf] respuesta PDF vacía")
            return None
        try:
            pdf_bytes = _b64.b64decode(b64)
        except Exception as exc:
            log_fn(f"  [amex-pdf] error decodificando base64: {exc}")
            return None
        if not pdf_bytes.startswith(b"%PDF"):
            log_fn(f"  [amex-pdf] respuesta no es PDF: {pdf_bytes[:20]!r}")
            return None
        return pdf_bytes

    def _import_resumen_amex(self, pdf_bytes: bytes, filename: str, log_fn) -> int:
        """Parsea un PDF de resumen AMEX e importa los gastos al DB."""
        import io
        from collections import Counter
        from db import insert_gastos, importacion_exists, importacion_exists_mes, _conn as _db_conn
        from parsers import PARSERS
        from categorizer import categorize_by_rules
        from user_config import read_user_config
        from scrapers_db import consolidate_scraper_duplicates

        fuente_target = "amex"
        if importacion_exists(fuente_target, filename):
            log_fn(f"  [amex-pdf] {filename} ya importado")
            return 0

        try:
            gastos = PARSERS["amex"].parse(io.BytesIO(pdf_bytes), filename)
        except Exception as exc:
            log_fn(f"  [amex-pdf] error parseando {filename}: {exc}")
            return 0

        if not gastos:
            log_fn(f"  [amex-pdf] {filename}: sin movimientos")
            return 0

        log_fn(f"  [amex-pdf] {filename}: {len(gastos)} movimientos parseados")

        # Chequear si este mes ya fue importado manualmente con otro nombre de archivo
        _fechas_tmp = [str(g.fecha)[:7] for g in gastos]
        mes_resumen_check = Counter(_fechas_tmp).most_common(1)[0][0] if _fechas_tmp else None
        if mes_resumen_check and importacion_exists_mes(fuente_target, mes_resumen_check):
            log_fn(f"  [amex-pdf] {filename}: mes {mes_resumen_check} ya importado — stub registrado")
            with _db_conn() as _c:
                _c.execute(
                    "INSERT INTO importaciones (fuente, archivo, mes_resumen, cantidad) VALUES (?,?,?,0)",
                    (fuente_target, filename, mes_resumen_check),
                )
            return 0

        user_cfg        = read_user_config()
        usuario_default = user_cfg["fuente_usuario"].get("amex")
        reglas_usuario  = user_cfg.get("reglas_usuario", [])
        _usuarios       = user_cfg.get("usuarios", ["Titular", "Adicional"])
        _persona_map    = {}
        if len(_usuarios) > 0: _persona_map["Titular"]  = _usuarios[0]
        if len(_usuarios) > 1: _persona_map["Adicional"] = _usuarios[1]

        records = []
        for g in gastos:
            cat = categorize_by_rules(g.descripcion, monto=float(g.monto), fuente=fuente_target)
            fuente_cat = "regla" if cat else None
            d = g.model_dump()
            d["categoria"]        = cat
            d["categoria_fuente"] = fuente_cat
            d["fuente"]           = fuente_target
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

        # Enriquecer gastos USD con TC del momento
        if any(r.get("moneda") == "USD" for r in records):
            from user_config import read_user_config, config_default
            from tc import fetch_tc_dolar
            _uc   = read_user_config()
            _tipo = _uc.get("tc_dolar_tipo") or config_default("tc_dolar_tipo") or "tarjeta"
            _tc   = fetch_tc_dolar(_tipo)
            if _tc:
                for r in records:
                    if r.get("moneda") == "USD":
                        r["tc_ars"] = _tc
                log_fn(f"  [amex-pdf] TC USD ({_tipo}): ${_tc:.2f}")

        parser      = PARSERS["amex"]
        import_info = {
            "fuente":         fuente_target,
            "archivo":        filename,
            "mes_resumen":    mes_resumen,
            "fecha_venc":     str(getattr(parser, "fecha_vencimiento", None) or "") or None,
            "total_ars":      float(getattr(parser, "stmt_total_ars", None) or 0) or None,
            "total_usd":      float(getattr(parser, "stmt_total_usd", None) or 0) or None,
            "proximo_cierre": str(getattr(parser, "proximo_cierre", None) or "") or None,
            "proximo_venc":   str(getattr(parser, "proximo_venc",   None) or "") or None,
        }
        count = insert_gastos(records, import_info=import_info)
        log_fn(f"  [amex-pdf] {filename}: {count} gastos insertados (mes={mes_resumen})")

        deduped = consolidate_scraper_duplicates(fuente_target, records)
        if deduped:
            log_fn(f"  [amex-pdf] {filename}: {deduped} duplicado(s) de scraper consolidados")

        return count

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_usd_amount(text: str) -> float:
        """
        Convierte importes USD del portal AMEX a float.

        El portal usa la notación argentina 'U$S' (no 'US$'):
          'U$S 20,00'      →  20.0
          'U$S 5.469,31'   →  5469.31
          'U$S 897,66'     →  897.66
        """
        if not text:
            return 0.0
        # Remover prefijo de moneda y espacios
        t = re.sub(r"U\$S\s*|US\$\s*|U\$\s*|\$\s*", "", text.strip(),
                   flags=re.IGNORECASE).strip()
        # Formato argentino: punto = miles, coma = decimal
        if "." in t and "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".")
        try:
            return float(t)
        except ValueError:
            return 0.0


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """
    Limpia el texto de una celda: elimina &nbsp; y espacios; devuelve '' si vacío.
    """
    return text.replace(_NBSP, "").strip() if text else ""

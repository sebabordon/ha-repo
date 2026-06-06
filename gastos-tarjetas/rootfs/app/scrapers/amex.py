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

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.americanexpress.com/es-ar/account/login"

_ACCOUNT_SUMMARY = (
    "https://global.americanexpress.com/myca/intl/acctsumm/canlac/"
    "accountSummary.do?request_type=&Face=es_AR"
)

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

    def do_login(self, driver, config: dict) -> None:
        """
        Login en la SPA React de AMEX AR.

        La página renderiza los inputs ~2-3 s después de la carga inicial.
        Algunos flows muestran usuario y contraseña en pantallas separadas
        (botón «Continuar» entre ambas); este código lo maneja.
        """
        logger.info("[amex] do_login: navegando a %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)

        # ── Usuario ───────────────────────────────────────────────────────────
        logger.info("[amex] do_login: esperando campo de usuario…")
        user_el = self.wait_for(
            driver,
            "input#eliloUserID, input[name='eliloUserID'], "
            "input[type='email'][autocomplete='username']",
            timeout=20,
        )
        logger.info("[amex] do_login: campo usuario encontrado, ingresando datos")
        user_el.clear()
        user_el.send_keys(config["usuario"])
        time.sleep(0.5)

        # ── Botón «Continuar» (si el flow separa usuario y contraseña) ────────
        pwd_visible = self.find(
            driver,
            "input#eliloPassword, input[name='eliloPassword'], "
            "input[type='password']",
        )
        logger.info("[amex] do_login: contraseña visible en pantalla inicial = %s", pwd_visible is not None)
        if not pwd_visible:
            cont_btn = self.find(
                driver,
                "button#loginSubmit, button[type='submit']",
            )
            if cont_btn:
                logger.info("[amex] do_login: haciendo click en Continuar (flow 2 pantallas)")
                cont_btn.click()
                time.sleep(2)

        # ── Contraseña ────────────────────────────────────────────────────────
        logger.info("[amex] do_login: esperando campo de contraseña…")
        pass_el = self.wait_for(
            driver,
            "input#eliloPassword, input[name='eliloPassword'], "
            "input[type='password']",
            timeout=15,
        )
        logger.info("[amex] do_login: campo contraseña encontrado, ingresando")
        pass_el.clear()
        pass_el.send_keys(config["password"])
        time.sleep(0.5)

        # ── Submit ────────────────────────────────────────────────────────────
        submit = self.wait_for(
            driver,
            "button#loginSubmit, button[type='submit'], input[type='submit']",
            timeout=10,
        )
        logger.info("[amex] do_login: haciendo click en Submit, esperando portal…")
        submit.click()

        # ── Esperar portal post-login ─────────────────────────────────────────
        # Puede llegar al portal legacy (JSP) o al dashboard moderno (React)
        self.wait_for(
            driver,
            # Portal legacy
            "div#middleContentHeader, div#leftNav, select#cardAccount, "
            # Dashboard moderno (fallback)
            "div[data-module-name='axp-account-summary'], "
            "[data-testid='account-summary']",
            timeout=45,
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

        # ── Secciones por cardholder ──────────────────────────────────────────
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
                # En el período abierto las filas NO vienen separadas por titular.
                # Solo es seguro asignar un cardholder si hay UN único titular;
                # con varios, atribuir todo al primero sería incorrecto, así que
                # se deja vacío y el import resuelve por el default de la fuente.
                default_ch = (
                    next(iter(cardholder_map.values())) if len(cardholder_map) == 1 else ""
                )
                if not default_ch and len(cardholder_map) > 1:
                    _l(f"[{nombre}] Fallback: {len(cardholder_map)} titulares — "
                       f"sin separación por titular, cardholder queda vacío")
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

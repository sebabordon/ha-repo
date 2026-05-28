"""
Scraper BBVA Argentina — híbrido Selenium + httpx.

Selenium: login en la SPA (micro-frontend React, complejo de automatizar).
httpx:    todas las llamadas a la API REST, usando las cookies que deja el login.

API base: https://online.bbva.com.ar/fnetcore/servicios/
Auth:     cookies de sesión generadas por el login (jsessionid + otras).

Credenciales:
  usuario     → número de DNI
  tercer_dato → nombre de usuario BBVA (el alias configurado en homebanking)
  password    → contraseña / clave

Endpoints:
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
import time
from datetime import datetime, timedelta, timezone

import httpx

from .base import BaseScraper, MovimientoRaw, ScraperResult

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.bbva.com.ar/personas/home.html"
_API_BASE  = "https://online.bbva.com.ar/fnetcore/servicios"

# Argentina — sin horario de verano
_ART = timezone(timedelta(hours=-3))

_DIAS_DEFAULT = 60
_PAGE_SIZE    = 10   # BBVA devuelve 10 movimientos por llamada (confirmado por HAR)

_HEADERS = {
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "es-AR,es;q=0.9",
    "Content-Type":     "application/json;charset=UTF-8",
    "Origin":           "https://www.bbva.com.ar",
    "Referer":          "https://www.bbva.com.ar/",
}

# Selectores de DNI — en orden de probabilidad
_DNI_SELECTORS = [
    "input#documentNumberInput",
    "input[name='documentNumber']",
    "input[id*='document' i]:not([type='hidden'])",
    "input[id*='dni' i]:not([type='hidden'])",
    "input[placeholder*='documento' i]",
    "input[placeholder*='DNI' i]",
    "input[type='tel']",
    "input[type='number']",
    "input[type='text']",  # último recurso: primer input de texto
]

# Selectores de usuario BBVA
_USER_SELECTORS = [
    "input#username",
    "input[name='username']",
    "input[autocomplete='username']",
    "input[placeholder*='usuario' i]",
    "input[id*='user' i]:not([type='hidden'])",
]

# Selectores de contraseña
_PASS_SELECTORS = [
    "input[type='password']",
    "input[name='password']",
    "input[autocomplete='current-password']",
]


def _ts() -> str:
    """Cache-buster en milisegundos, igual que el frontend de BBVA."""
    return str(int(time.time() * 1000))


class BbvaScraper(BaseScraper):
    fuente       = "bbva"
    nombre       = "BBVA Argentina"
    login_origin = "https://www.bbva.com.ar"

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

    def _find_across_frames(self, driver, selectors: list[str]):
        """
        Busca el primer elemento que matchee cualquiera de los selectores,
        probando el frame actual primero y luego cada iframe del DOM.

        Si lo encuentra en un iframe, el driver queda enfocado en ese iframe
        (para que las interacciones siguientes funcionen en el mismo contexto).
        Si no lo encuentra en ningún lado, resetea a default_content.

        Returns: (element, in_frame: bool) o (None, False)
        """
        # Frame actual (default)
        for sel in selectors:
            el = self.find(driver, sel)
            if el:
                return el, False

        # Cada iframe de primer nivel
        iframes = driver.find_elements("css selector", "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                for sel in selectors:
                    el = self.find(driver, sel)
                    if el:
                        return el, True          # dejamos el driver en este frame
            except Exception:
                pass
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return None, False

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
        Login en la SPA de BBVA con Selenium.

        BBVA muestra un formulario en (al menos) dos pasos:
          Paso 1: tipo de documento (DNI) + número de documento → Continuar
          Paso 2: nombre de usuario + contraseña → Ingresar

        El formulario puede estar en un iframe (patrón habitual en SPAs BBVA).
        `_find_across_frames` detecta y cambia al iframe correcto automáticamente.
        Si el login falla, se emite diagnóstico completo al log (inputs, iframes,
        body HTML) para facilitar la calibración de selectores.
        """
        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        logger.info("[bbva] cargando login: %s", _LOGIN_URL)
        driver.get(_LOGIN_URL)
        time.sleep(6)   # SPA React + lazy-loading de micro-frontends

        # ── Diagnóstico inicial ───────────────────────────────────────────────
        self._dump_page_state(driver)

        # ── Paso 1: número de DNI ─────────────────────────────────────────────
        dni_el, in_frame = self._find_across_frames(driver, _DNI_SELECTORS)
        if in_frame:
            logger.info("[bbva] campo DNI encontrado en iframe")

        if dni_el is None:
            # Estado extra: si estamos en un iframe, dumpeamos su contenido también
            logger.warning(
                "[bbva] No se encontró el campo DNI. "
                "Revisá los logs [bbva-diag] para ver la estructura real de la página."
            )
            raise RuntimeError(
                "[bbva] campo DNI no encontrado tras 6 s. "
                "Mirá los mensajes [bbva-diag] en el log del add-on."
            )

        logger.info("[bbva] llenando DNI")
        try:
            dni_el.clear()
        except Exception:
            pass
        dni_el.send_keys(dni)
        time.sleep(0.5)

        # Botón "Continuar" / "Siguiente" (paso 1 → paso 2)
        btn_cont = self.find(driver,
            "#login-button, "
            "button[id*='continu' i], button[id*='next' i], "
            "button[type='submit']"
        )
        if btn_cont:
            try:
                btn_cont.click()
                logger.info("[bbva] clic en botón continuar")
                time.sleep(3)
            except Exception:
                pass

        # ── Paso 2: usuario BBVA ──────────────────────────────────────────────
        if username:
            user_el, _ = self._find_across_frames(driver, _USER_SELECTORS)
            if user_el:
                logger.info("[bbva] llenando usuario BBVA")
                try:
                    user_el.clear()
                except Exception:
                    pass
                user_el.send_keys(username)
                time.sleep(0.5)
            else:
                logger.warning("[bbva] campo de usuario no encontrado (puede no existir en esta pantalla)")

        # ── Paso 2: contraseña ────────────────────────────────────────────────
        pass_el, _ = self._find_across_frames(driver, _PASS_SELECTORS)
        if pass_el is None:
            self._dump_page_state(driver)
            raise RuntimeError(
                "[bbva] campo de contraseña no encontrado. "
                "Mirá los mensajes [bbva-diag] en el log del add-on."
            )

        logger.info("[bbva] llenando contraseña")
        try:
            pass_el.clear()
        except Exception:
            pass
        pass_el.send_keys(password)
        time.sleep(0.5)

        # Submit
        submit_el, _ = self._find_across_frames(driver, ["button[type='submit']"])
        if submit_el is None:
            raise RuntimeError("[bbva] botón Submit no encontrado")

        submit_el.click()
        logger.info("[bbva] submit enviado — esperando cookies de sesión")

        # BBVA tarda varios segundos en emitir el jsessionid definitivo
        time.sleep(10)

        # ── Verificar sesión activa vía API ────────────────────────────────────
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        cookies = self._driver_cookies(driver)
        logger.info("[bbva] cookies post-login: %d", len(cookies))

        if cookies:
            try:
                with self._make_client(cookies) as client:
                    resp = client.get(
                        f"{_API_BASE}/cliente/datosperfil",
                        params={"ts": _ts()},
                    )
                if resp.status_code == 200:
                    perfil = (
                        (resp.json().get("result") or {})
                        .get("perfilCliente", {})
                    )
                    nombre = perfil.get("nombre", "?")
                    logger.info("[bbva] Login OK — usuario: %s", nombre)
                    return
                else:
                    logger.warning("[bbva] datosperfil HTTP %d post-login", resp.status_code)
            except Exception as exc:
                logger.info("[bbva] API post-login error: %s", exc)

        raise RuntimeError(
            "[bbva] Login completado pero la API no responde. "
            "Verificá usuario (DNI), nombre de usuario y contraseña."
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

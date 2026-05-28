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

        BBVA muestra un formulario en dos pasos:
          Paso 1: tipo de documento (DNI) + número de documento → Continuar
          Paso 2: nombre de usuario + contraseña → Ingresar

        El script espera la secuencia normal; si BBVA devuelve un error o una
        pantalla inesperada lanzará TimeoutException (que el scheduler registra
        como error de sesión).
        """
        dni      = config["usuario"]
        username = config.get("tercer_dato", "")
        password = config["password"]

        driver.get(_LOGIN_URL)
        time.sleep(3)

        # ── Paso 1: número de DNI ─────────────────────────────────────────────
        # Selector confirmado por análisis del HTML de login de BBVA
        dni_el = self.wait_for(driver, "input#documentNumberInput", timeout=20)
        dni_el.clear()
        dni_el.send_keys(dni)
        time.sleep(0.5)

        # Botón para continuar al paso 2 (puede llamarse "Continuar" o "Siguiente")
        btn_cont = self.find(driver,
            "#login-button, button[id*='continu' i], button[id*='next' i], "
            "button[type='submit']"
        )
        if btn_cont:
            try:
                btn_cont.click()
                time.sleep(2)
            except Exception:
                pass

        # ── Paso 2: usuario BBVA ──────────────────────────────────────────────
        if username:
            user_el = self.find(driver,
                "input#username, input[name='username'], "
                "input[autocomplete='username'], "
                "input[placeholder*='usuario' i]"
            )
            if user_el:
                user_el.clear()
                user_el.send_keys(username)
                time.sleep(0.5)

        # ── Paso 2: contraseña ────────────────────────────────────────────────
        pass_el = self.wait_for(driver,
            "input[type='password'], input[name='password'], "
            "input[autocomplete='current-password']",
            timeout=15,
        )
        pass_el.clear()
        pass_el.send_keys(password)
        time.sleep(0.5)

        # Submit
        submit = self.wait_for(driver, "button[type='submit']", timeout=10)
        submit.click()

        # Esperar que la SPA termine de cargar y las cookies de sesión queden
        # listas (BBVA tarda varios segundos en emitir el jsessionid definitivo)
        time.sleep(10)

        # Verificar sesión activa vía API
        cookies = self._driver_cookies(driver)
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
            except Exception as exc:
                logger.info("[bbva] API post-login: %s", exc)

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

            result    = resp.json().get("result", {})
            cajas     = result.get("cajasAhorro", [])
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

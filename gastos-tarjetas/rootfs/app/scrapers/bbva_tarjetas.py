"""
Scraper BBVA Argentina — Tarjetas de Crédito (Visa y Mastercard).

Misma estrategia que el scraper de cuentas (bbva.py): hereda BbvaScraper
para login / sesión / _api_request y solo overridea scrape().

Flujo (confirmado por HAR bbvalogin6.har):
  1. GET  /cliente/productos/tarjetas
       → lista tarjetasCreditoVisa / tarjetasCreditoMastercard
       → cada item tiene `id` (numérico) y `numeroPan` (token opaco)
  2. GET  /cards/v1/cards/{numeroPan}/transactions
       → array `data[]` con los consumos del período en curso
       → campos: localAmount.{amount,currency}, concept, operationDate
  3. GET  /cliente/productos/tarjetas/{id}/datosultimoproximoresumen
       → result.estadoActual.{saldoPesos, saldoDolares}

Tarjetas soportadas:
  tarjetasCreditoVisa        → fuente "bbva_visa"
  tarjetasCreditoMastercard  → fuente "bbva_mc"

El mapeo tarjeta→fuente se puede overridear vía __cuentas__ del scheduler
usando product_key="VISA" o product_key="MC".
"""

import logging
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from .base import MovimientoRaw, ScraperResult
from .bbva import BbvaScraper

logger = logging.getLogger(__name__)

_FUENTE_VISA = "bbva_visa"
_FUENTE_MC   = "bbva_mc"

_EP_TARJETAS   = "/cliente/productos/tarjetas"
_EP_TRANSACC   = "/cards/v1/cards/{pan}/transactions"
_EP_RESUMEN    = "/cliente/productos/tarjetas/{id}/datosultimoproximoresumen"

# Detecta tipo de tarjeta por nombre de clave en la API
_VISA_RE = re.compile(r"\bvisa\b",        re.IGNORECASE)
_MC_RE   = re.compile(r"\bmastercard\b",  re.IGNORECASE)

# Tipos de transacción que son pagos/créditos (monto negativo)
_CREDITO_TYPES = {"PAYMENT", "CREDIT", "PAGO", "CREDITO", "REFUND", "REVERSAL"}


class BbvaTarjetasScraper(BbvaScraper):
    fuente = "bbva_tarjetas"
    nombre = "BBVA Argentina — Tarjetas de Crédito"

    # ── scrape ────────────────────────────────────────────────────────────────

    def scrape(self, driver, config: dict) -> ScraperResult:
        log: list[str] = []

        def _log(msg: str) -> None:
            logger.info("[bbva-tj] %s", msg)
            log.append(msg)

        # Resolver fuentes (defaults + override por __cuentas__)
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

        usuario_default = (config.get("usuario_default") or "").strip() or None

        movimientos: list[MovimientoRaw] = []
        saldos: dict = {}

        # ── 1. Lista de tarjetas ──────────────────────────────────────────────
        resp = self._api_request(driver, _EP_TARJETAS)
        _log(f"GET {_EP_TARJETAS} → HTTP {resp['status']}")
        if resp["status"] != 200 or not resp["json"]:
            _log("⚠ No se pudo obtener la lista de tarjetas")
            return ScraperResult(fuente=self.fuente, movimientos=[], log_lines=log)

        tarjetas = self._extract_tarjetas(resp["json"], _log)
        _log(f"Tarjetas encontradas: {len(tarjetas)}")

        # ── 2. Consumos + saldo por tarjeta ───────────────────────────────────
        for tj in tarjetas:
            tipo   = tj["tipo"]
            nombre = tj["nombre"]
            fuente = product_to_fuente.get(tipo)
            if not fuente:
                _log(f"  Saltando {nombre} (tipo={tipo} sin mapeo)")
                continue

            _log(f"  Procesando {nombre} → fuente={fuente}")
            try:
                movs, saldo = self._fetch_tarjeta(driver, tj, fuente, usuario_default, _log)
                movimientos.extend(movs)
                if saldo is not None:
                    saldos[fuente] = {"saldo_ars": saldo}
                _log(f"  → {len(movs)} consumos, saldo={saldo}")
            except Exception as exc:
                _log(f"  ✗ Error en {nombre}: {exc}")
                logger.exception("[bbva-tj] Error scrapeando %s", nombre)

        if config.get("auto_resumenes"):
            self._scrape_resumenes(driver, product_to_fuente, config, _log)

        return ScraperResult(
            fuente      = self.fuente,
            movimientos = movimientos,
            saldos      = saldos,
            log_lines   = log,
        )

    # ── Extracción de tarjetas del JSON ──────────────────────────────────────

    def _extract_tarjetas(self, json_body: dict, log_fn) -> list[dict]:
        """
        Parsea GET /cliente/productos/tarjetas.
        Itera sobre las claves del result que contengan "credito" en el nombre
        (tarjetasCreditoVisa, tarjetasCreditoMastercard) y deduce el tipo
        (VISA / MC) del nombre de la clave.
        Extrae id, numeroPan y nombre de cada item.
        """
        result = json_body.get("result") or json_body
        if not isinstance(result, dict):
            log_fn(f"  [diag] result inesperado: {str(json_body)[:300]}")
            return []

        tarjetas = []
        for key, items in result.items():
            if not isinstance(items, list) or not items:
                continue
            kl = key.lower()
            if "debito" in kl or "debit" in kl:
                continue  # ignorar tarjetas de débito
            if "credito" not in kl and "credit" not in kl and "card" not in kl:
                continue

            tipo = "VISA" if _VISA_RE.search(key) else ("MC" if _MC_RE.search(key) else None)
            log_fn(f"  Clave '{key}': {len(items)} items (tipo={tipo})")

            for item in items:
                id_tj     = str(item.get("id") or item.get("idProducto") or "")
                numero_pan = str(item.get("numeroPan") or "")
                numero    = item.get("numero") or ""

                if not id_tj or not numero_pan:
                    log_fn(f"  ⚠ Item sin id o numeroPan: {item}")
                    continue

                # Tipo desde la clave; fallback por campos del item
                t = tipo
                if t is None:
                    texto = " ".join(str(item.get(k) or "") for k in
                                     ("alias", "descripcion", "marca", "brand"))
                    t_sub = item.get("tipoProducto") or {}
                    texto += " " + str(t_sub.get("descripcion") or "")
                    if _VISA_RE.search(texto):   t = "VISA"
                    elif _MC_RE.search(texto):   t = "MC"
                    else:
                        log_fn(f"  Tipo no reconocido: {str(item)[:200]}")
                        continue

                nombre = (
                    item.get("alias") or
                    (item.get("tipoProducto") or {}).get("descripcion") or
                    ("Visa" if t == "VISA" else "Mastercard")
                )

                tarjetas.append({
                    "id":        id_tj,
                    "pan":       numero_pan,
                    "tipo":      t,
                    "nombre":    f"{nombre} {numero}".strip()[:80],
                })
                log_fn(f"  Tarjeta: tipo={t} nombre={nombre!r} num={numero} id={id_tj}")

        return tarjetas

    # ── tsec + llamada autenticada a /cards/v1/ ───────────────────────────────

    _EP_TSEC = "/seguridad/cliente/obtenerTsec"

    def _fetch_tsec(self, driver) -> Optional[str]:
        """
        Llama GET /seguridad/cliente/obtenerTsec y extrae el JWT del header
        'tsec' de la respuesta (no del body).

        El endpoint devuelve el token como response header, no como body.
        Necesita un fetch() modificado que capture los headers de la respuesta.
        """
        _API_BASE = "https://online.bbva.com.ar/fnetcore/servicios"
        ts_ms = str(int(time.time() * 1000))
        url   = f"{_API_BASE}{self._EP_TSEC}?ts={ts_ms}"

        js = """
        var url = arguments[0];
        var cb  = arguments[arguments.length - 1];

        // Leer XSRF-TOKEN de cookies
        var xsrf = null;
        try {
            document.cookie.split(';').forEach(function(c) {
                var p = c.trim();
                if (p.startsWith('XSRF-TOKEN='))
                    xsrf = decodeURIComponent(p.substring(11));
            });
        } catch(e) {}

        var opts = {
            method: 'GET',
            headers: {
                'Accept':          'application/json, text/plain, */*',
                'Accept-Language': 'es-AR,es;q=0.9'
            },
            credentials: 'include'
        };
        if (xsrf) opts.headers['X-XSRF-TOKEN'] = xsrf;

        fetch(url, opts)
            .then(function(r) {
                var tsec = r.headers.get('tsec') || '';
                return r.text().then(function(t) {
                    cb({status: r.status, tsec: tsec, body: t});
                });
            })
            .catch(function(e) {
                cb({status: 0, tsec: '', body: 'fetch error: ' + e});
            });
        """
        try:
            driver.set_script_timeout(35)
        except Exception:
            pass
        try:
            result = driver.execute_async_script(js, url)
            tsec = (result or {}).get("tsec") or ""
            status = (result or {}).get("status", 0)
            return tsec if tsec else None
        except Exception as exc:
            logger.warning("[bbva-tj] _fetch_tsec error: %s", exc)
            return None

    def _api_request_cards(self, driver, path: str) -> dict:
        """
        GET a un endpoint de /cards/v1/ con los headers extra que requiere:
          tsec          — JWT obtenido de /seguridad/cliente/obtenerTsec
          timestamp-uid — timestamp actual en hora Argentina (formato ISO-0300)
          uid           — UUID v4 aleatorio por request
          X-XSRF-TOKEN  — igual que _api_request normal
        """
        _API_BASE = "https://online.bbva.com.ar/fnetcore/servicios"
        ts_ms = str(int(time.time() * 1000))
        url   = f"{_API_BASE}{path}?ts={ts_ms}"

        # Hora Argentina (UTC-3)
        art_now  = datetime.now(timezone(timedelta(hours=-3)))
        ts_uid   = art_now.strftime("%Y-%m-%dT%H:%M:%S-0300")
        req_uid  = str(uuid.uuid4())

        # Obtener tsec fresh
        tsec = self._fetch_tsec(driver) or ""

        js = """
        var url    = arguments[0];
        var tsec   = arguments[1];
        var tsUid  = arguments[2];
        var uid    = arguments[3];
        var cb     = arguments[arguments.length - 1];

        var xsrf = null;
        try {
            document.cookie.split(';').forEach(function(c) {
                var p = c.trim();
                if (p.startsWith('XSRF-TOKEN='))
                    xsrf = decodeURIComponent(p.substring(11));
            });
        } catch(e) {}

        var opts = {
            method: 'GET',
            headers: {
                'Accept':          'application/json, text/plain, */*',
                'Accept-Language': 'es-419,es;q=0.9,en;q=0.8',
                'timestamp-uid':   tsUid,
                'uid':             uid
            },
            credentials: 'include'
        };
        if (xsrf) opts.headers['X-XSRF-TOKEN'] = xsrf;
        if (tsec) opts.headers['tsec']          = tsec;

        fetch(url, opts)
            .then(function(r) {
                return r.text().then(function(t) {
                    cb({status: r.status, body: t});
                });
            })
            .catch(function(e) {
                cb({status: 0, body: 'fetch error: ' + e});
            });
        """
        try:
            driver.set_script_timeout(35)
        except Exception:
            pass
        try:
            result = driver.execute_async_script(js, url, tsec, ts_uid, req_uid)
            status = int((result or {}).get("status", 0) or 0)
            body   = str((result or {}).get("body", "") or "")
            parsed = None
            try:
                import json as _json
                parsed = _json.loads(body) if body else None
            except Exception:
                pass
            return {"status": status, "body": body, "json": parsed}
        except Exception as exc:
            logger.warning("[bbva-tj] _api_request_cards error: %s", exc)
            return {"status": 0, "body": str(exc), "json": None}

    # ── Fetch de una tarjeta: saldo + consumos ────────────────────────────────

    def _fetch_tarjeta(
        self,
        driver,
        tj: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
    ) -> tuple[list[MovimientoRaw], Optional[float]]:

        id_tj = tj["id"]
        pan   = tj["pan"]

        # Saldo actual
        saldo = self._fetch_saldo(driver, id_tj, log_fn)

        # Consumos del período — requiere headers tsec/uid/timestamp-uid
        ep = _EP_TRANSACC.format(pan=pan)
        resp = self._api_request_cards(driver, ep)
        log_fn(f"  GET {ep} → HTTP {resp['status']}")

        if resp["status"] != 200 or not resp["json"]:
            log_fn(f"  ⚠ Sin respuesta válida — body: {resp['body'][:300]}")
            return [], saldo

        movs = self._parse_transactions(
            resp["json"], fuente, usuario_default, log_fn, tj["nombre"]
        )
        return movs, saldo

    def _fetch_saldo(self, driver, id_tj: str, log_fn) -> Optional[float]:
        ep   = _EP_RESUMEN.format(id=id_tj)
        resp = self._api_request(driver, ep)
        log_fn(f"  GET {ep} → HTTP {resp['status']}")
        if resp["status"] != 200 or not resp["json"]:
            return None
        try:
            estado = (resp["json"].get("result") or {}).get("estadoActual") or {}
            s = estado.get("saldoPesos") or estado.get("saldoDolares")
            if s:
                val = float(str(s).replace(",", "."))
                log_fn(f"  Saldo ARS: {val}")
                return val
        except (ValueError, TypeError):
            pass
        return None

    # ── Auto-descarga de resúmenes PDF ────────────────────────────────────────

    _EP_EXTRACTOS = "/cliente/extractos/extractos"
    _EP_GETPDF    = "/cliente/extractos/getPdf"

    def _fetch_extractos(self, driver, log_fn) -> list[dict]:
        """
        POST /extractos/extractos {"fecha":"YYYY"} → lista de resúmenes.
        Devuelve la lista de extractos (cada uno con 'reporte', 'fechaCierre', 'detalle').
        """
        from datetime import datetime
        year = str(datetime.now().year)
        resp = self._api_request(
            driver, self._EP_EXTRACTOS, method="POST", json_body={"fecha": year}
        )
        if resp["status"] != 200 or not resp["json"]:
            log_fn(f"  [extractos] HTTP {resp['status']} — {resp['body'][:200]}")
            return []
        extractos = ((resp["json"].get("result") or {}).get("extractos") or [])
        log_fn(f"  [extractos] {len(extractos)} disponibles (año {year})")
        return extractos

    def _fetch_pdf_bytes(self, driver, reporte: str, log_fn) -> Optional[bytes]:
        """
        POST /extractos/getPdf {"reporte":"..."} → bytes del PDF.
        Usa fetch() + arrayBuffer() dentro del browser y transfiere como base64.
        """
        import base64 as _b64
        _API_BASE = "https://online.bbva.com.ar/fnetcore/servicios"
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
        Replica la lógica de upload.py pero en contexto síncrono (no async),
        usando categorize_by_rules en lugar del categorize async.
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
            cat, fuente_cat = categorize_by_rules(g.descripcion, monto=eff_monto, fuente=fuente_target)
            d = g.model_dump()
            d["categoria"]       = cat
            d["categoria_fuente"] = fuente_cat
            d["fuente"]          = fuente_target
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
            "fuente":          fuente_target,
            "archivo":         filename,
            "mes_resumen":     mes_resumen,
            "fecha_venc":      str(fecha_venc)      if fecha_venc      else None,
            "total_ars":       float(stmt_ars)       if stmt_ars        else None,
            "total_usd":       float(stmt_usd)       if stmt_usd        else None,
            "proximo_cierre":  str(proximo_cierre)   if proximo_cierre  else None,
            "proximo_venc":    str(proximo_venc)     if proximo_venc    else None,
        }
        count = insert_gastos(records, import_info=import_info)
        log_fn(f"  [import] {filename}: {count} gastos insertados (mes={mes_resumen})")

        _RESUMEN_PARSERS = frozenset({"amex", "bbva_mc", "bbva_visa"})
        if parser_key in _RESUMEN_PARSERS:
            deduped = consolidate_scraper_duplicates(fuente_target, records)
            if deduped:
                log_fn(f"  [import] {filename}: {deduped} duplicado(s) de scraper consolidados")

        return count

    def _scrape_resumenes(
        self,
        driver,
        product_to_fuente: dict,
        config: dict,
        log_fn,
    ) -> None:
        """
        Revisa si hay resúmenes VISA/MC nuevos y los importa.
        Por cada tipo de tarjeta (VISA, MC) importa como máximo el resumen
        más reciente que aún no esté en importaciones.
        """
        from db import importacion_exists

        log_fn("Buscando resúmenes PDF nuevos…")
        extractos = self._fetch_extractos(driver, log_fn)
        if not extractos:
            return

        # "importado" per tipo para no procesar más de uno por run si hay varios nuevos
        done: set[str] = set()

        for ex in extractos:
            detalle = (ex.get("detalle") or "").upper()
            reporte = (ex.get("reporte") or "").strip()
            if not reporte:
                continue

            if "VISA" in detalle and "MASTERCARD" not in detalle:
                product_key = "VISA"
                parser_key  = "bbva_visa"
            elif "MASTERCARD" in detalle:
                product_key = "MC"
                parser_key  = "bbva_mc"
            else:
                continue

            if product_key in done:
                continue

            fuente_target = product_to_fuente.get(product_key, parser_key)
            filename      = f"BBVA_{product_key}_{reporte}_auto.pdf"

            if importacion_exists(fuente_target, filename):
                log_fn(f"  [{product_key}] al día ({ex.get('fechaCierre')})")
                done.add(product_key)
                continue

            log_fn(f"  [{product_key}] descargando resumen {ex.get('fechaCierre')} (reporte={reporte})…")
            pdf_bytes = self._fetch_pdf_bytes(driver, reporte, log_fn)
            if not pdf_bytes:
                done.add(product_key)
                continue

            log_fn(f"  [{product_key}] PDF descargado ({len(pdf_bytes):,} bytes), importando…")
            self._import_resumen(pdf_bytes, filename, parser_key, fuente_target, config, log_fn)
            done.add(product_key)

            if len(done) == 2:
                break

    # ── Parseo de transacciones ───────────────────────────────────────────────

    def _parse_transactions(
        self,
        json_body: dict,
        fuente: str,
        usuario_default: Optional[str],
        log_fn,
        nombre_tarjeta: str,
    ) -> list[MovimientoRaw]:
        """
        Parsea la respuesta de GET /cards/v1/cards/{pan}/transactions.

        Estructura (confirmada por HAR):
          {
            "data": [
              {
                "localAmount":   {"amount": "5089.98", "currency": "ARS"},
                "concept":       "CONSUMO EN PESOS",
                "operationDate": "2026-06-03T00:00:00.000-0300",
                "transactionType": {"id": "AUTHORIZED", ...},
                "status":        {"id": "SETTLED", ...},
                ...
              }, ...
            ]
          }

        Convención de monto: positivo = egreso (cargo), negativo = crédito.
        Los consumos tipo "AUTHORIZED"/"SETTLED" son egresos; pagos/créditos
        se detectan por transactionType.id.
        """
        items = json_body.get("data") or []
        if not items:
            log_fn(f"  [diag] Sin items en 'data'. Keys: {list(json_body.keys())}")
            return []

        log_fn(f"  Transacciones en respuesta: {len(items)}")

        movimientos = []
        for item in items:
            # Log tx_type para cada transacción (diagnóstico de signo)
            concept  = (item.get("concept") or "").strip()[:40]
            tx_raw   = (item.get("transactionType") or {})
            tx_id    = str(tx_raw.get("id") or "").upper()
            tx_desc  = str(tx_raw.get("description") or "")
            amount   = (item.get("localAmount") or {}).get("amount", "?")
            log_fn(f"  [tx] {concept!r:42s} type={tx_id!r} ({tx_desc}) amount={amount}")

            mov = self._parse_one(item, fuente, usuario_default, nombre_tarjeta)
            if mov:
                movimientos.append(mov)

        return movimientos

    def _parse_one(
        self,
        item: dict,
        fuente: str,
        usuario_default: Optional[str],
        nombre_tarjeta: str,
    ) -> Optional[MovimientoRaw]:

        # Fecha — "2026-06-03T00:00:00.000-0300"
        fecha_raw = (
            item.get("operationDate") or
            item.get("accountedDate") or
            item.get("valuationDate") or ""
        )
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(fecha_raw))
        if not m:
            return None
        fecha_iso = m.group(1)

        # Descripción
        desc = (item.get("concept") or "").strip()
        if not desc:
            return None

        # Monto y moneda
        local = item.get("localAmount") or {}
        try:
            monto = float(str(local.get("amount") or 0).replace(",", "."))
        except (ValueError, TypeError):
            return None
        if monto == 0:
            return None

        moneda = "USD" if "USD" in str(local.get("currency") or "").upper() else "ARS"

        # Signo: créditos/pagos → monto negativo.
        # Se aplica en dos pasos:
        # 1. Si tx_type es explícitamente un crédito → negativo.
        # 2. Si la API ya mandó el monto negativo (ej. SU PAGO EN PESOS con
        #    tx_type desconocido) → respetar ese signo negativo en lugar de
        #    forzar abs(). Esto evita que abs() convierta pagos en egresos.
        tx_type = str((item.get("transactionType") or {}).get("id") or "").upper()
        if tx_type in _CREDITO_TYPES or monto < 0:
            monto = -abs(monto)
        else:
            monto = abs(monto)

        raw_data: dict = {"tarjeta": nombre_tarjeta, "tx_type": tx_type}
        if usuario_default:
            raw_data["usuario"] = usuario_default
        status = (item.get("status") or {}).get("id")
        if status:
            raw_data["status"] = status

        return MovimientoRaw(
            fuente      = fuente,
            fecha       = fecha_iso,
            descripcion = desc[:200],
            monto       = monto,
            moneda      = moneda,
            raw_data    = raw_data,
        )

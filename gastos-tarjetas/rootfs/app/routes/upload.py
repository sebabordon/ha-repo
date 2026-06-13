import io
import logging
from collections import Counter

from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException

from auth import require_auth

logger = logging.getLogger(__name__)
from categorizer import categorize
from db import insert_gastos, upsert_cuenta_saldo, _CC_FUENTES, importacion_exists
from parsers import PARSERS
from user_config import read_user_config

router = APIRouter()


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    fuente: str = Form(...),
    include_rg5617_credits: str = Form("false"),
    target_fuente: str = Form(None),
):
    """
    `fuente` = parser key (qué parser usar para parsear el archivo).
    `target_fuente` = (opcional, v0.4.4+) `fuente` con la que se guardan los
                      gastos.  Por defecto = `fuente`.  Útil cuando una cuenta
                      con slug custom (ej. "bbva_pesos_personal") usa el parser
                      "bbva_cuenta" pero querés que los gastos queden bajo su
                      propio slug.
    """
    require_auth(request)

    if fuente not in PARSERS:
        raise HTTPException(400, f"Fuente desconocida: {fuente}. Opciones: {list(PARSERS)}")

    # Si no se pasa target_fuente, gastos van con la misma fuente del parser
    effective_fuente = (target_fuente or fuente).strip()

    filename_key = file.filename or effective_fuente
    if importacion_exists(effective_fuente, filename_key):
        return {
            "importados": 0,
            "total_parseados": 0,
            "ya_importado": True,
            "mensaje": f"Este archivo ya fue importado anteriormente: {filename_key}",
        }

    content = await file.read()

    try:
        gastos = PARSERS[fuente].parse(io.BytesIO(content), file.filename)
    except Exception as e:
        raise HTTPException(422, f"Error al parsear archivo: {e}")

    if not gastos:
        return {"importados": 0, "total_parseados": 0, "mensaje": "No se encontraron movimientos en el archivo."}

    # Filter RG 5617 credit/return entries (DEV PERCEPCION, CR.RG) unless the
    # caller explicitly opted in.  These returns cancel out the previous period's
    # perception charge when the cardholder pays their USD balance in USD, so
    # importing them would create phantom income entries.
    if include_rg5617_credits.lower() not in ("true", "1", "yes"):
        gastos = [g for g in gastos if not ("5617" in g.descripcion and g.monto < 0)]

    user_cfg        = read_user_config()
    usuario_default = user_cfg["fuente_usuario"].get(fuente)
    reglas_usuario  = user_cfg.get("reglas_usuario", [])
    # Map parser's hardcoded persona slots to whatever names the user configured.
    # Parsers always emit "Titular" (slot 0) or "Adicional" (slot 1); translate
    # those to the actual configured persona names so renames are respected.
    _usuarios = user_cfg.get("usuarios", ["Titular", "Adicional"])
    _parser_persona_map = {}
    if len(_usuarios) > 0: _parser_persona_map["Titular"]  = _usuarios[0]
    if len(_usuarios) > 1: _parser_persona_map["Adicional"] = _usuarios[1]

    # Non-CC parsers return negative monto for expenses; normalize to positive=egreso.
    needs_flip = fuente not in _CC_FUENTES

    records = []
    for g in gastos:
        # Normalize to our sign convention (>0=egreso) before categorizing so
        # that solo_egresos rules fire correctly for non-CC parsers too.
        eff_monto = -float(g.monto) if (needs_flip and g.monto != 0) else float(g.monto)
        cat, fuente_cat = await categorize(g.descripcion, monto=eff_monto, fuente=effective_fuente)
        d = g.model_dump()
        d["categoria"] = cat
        d["categoria_fuente"] = fuente_cat
        # Override fuente con effective_fuente (= target_fuente si se pasó,
        # sino = fuente del parser).  Esto permite que cuentas con slug custom
        # usen un parser estándar pero conserven su propio fuente.
        d["fuente"] = effective_fuente
        if needs_flip and d["monto"] != 0:
            d["monto"] = -float(d["monto"])
        if g.usuario is not None:
            # Parser detected a specific person (e.g. additional cardholder).
            # Translate hardcoded slot name ("Adicional") to the user-configured name.
            d["usuario"] = _parser_persona_map.get(g.usuario, g.usuario)
        else:
            # Try user classification rules first, then fall back to source default
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

    # Detect the most common month in the imported records (statement month)
    fechas = [str(r.get("fecha", ""))[:7] for r in records if r.get("fecha")]
    mes_resumen = Counter(fechas).most_common(1)[0][0] if fechas else None

    fecha_venc      = getattr(PARSERS[fuente], "fecha_vencimiento", None)
    stmt_ars        = getattr(PARSERS[fuente], "stmt_total_ars",    None)
    stmt_usd        = getattr(PARSERS[fuente], "stmt_total_usd",    None)
    proximo_cierre  = getattr(PARSERS[fuente], "proximo_cierre",    None)
    proximo_venc    = getattr(PARSERS[fuente], "proximo_venc",      None)

    # ── Synthetic "Créditos del resumen" adjustment ─────────────────────────────
    # When the parser detected the statement's TOTAL A PAGAR / SALDO ACTUAL,
    # insert a balancing row so that net(all ARS transactions) == statement total.
    #
    # Use the NET (positive egresos + negative ingresos already imported) so that
    # credits already present as individual rows (BONIF, ML returns, CR.RG …)
    # are NOT double-counted.  If they already close the gap the delta is ~0 and
    # no synthetic row is inserted.  A residual delta arises only from factors
    # outside the current-period transactions (e.g. a BBVA overpayment carry-over
    # from the previous billing cycle that isn't a line item in "Nuevos Cargos").
    ajuste_ars: float | None = None
    if stmt_ars is not None:
        # Exclude RG 5617 credit rows from the delta base so that importing
        # DEV PERCEPCION / CR.RG entries doesn't inflate the net and suppress
        # the synthetic adjustment row.  The widget uses the same exclusion so
        # "total to pay" is consistent regardless of whether 5617 credits were
        # imported.
        net_ars_imported = sum(
            float(r["monto"]) for r in records
            if r.get("moneda") == "ARS"
            and not ("5617" in (r.get("descripcion") or "") and float(r.get("monto", 0)) < 0)
        )
        delta = round(float(stmt_ars) - net_ars_imported, 2)
        # Only insert the synthetic row for NEGATIVE deltas (the statement charges
        # you LESS than the sum of all imported transactions, meaning there is a
        # genuine credit/overpayment applied by the card company that has no
        # individual transaction row).
        # Positive delta = statement charges MORE than net transactions = previous-
        # period balance carryover that cannot be expressed as a single transaction;
        # adding it as an egreso row would be misleading.
        if delta < -0.5:
            adj_fecha = (mes_resumen + "-01") if mes_resumen else str(fecha_venc or "")
            records.append({
                "fecha":           adj_fecha,
                "descripcion":     "Créditos del resumen",
                "monto":           str(delta),   # negative = ingreso (credit/overpayment)
                "moneda":          "ARS",
                "fuente":          effective_fuente,
                "categoria":       "Créditos tarjeta",
                "categoria_fuente": "auto",
                "archivo_origen":  file.filename or effective_fuente,
                "usuario":         usuario_default,
            })
            ajuste_ars = delta

    import_info = {
        "fuente":          effective_fuente,
        "archivo":         file.filename or effective_fuente,
        "mes_resumen":     mes_resumen,
        "fecha_venc":      str(fecha_venc)       if fecha_venc      else None,
        "total_ars":       float(stmt_ars)        if stmt_ars        else None,
        "total_usd":       float(stmt_usd)        if stmt_usd        else None,
        "proximo_cierre":  str(proximo_cierre)    if proximo_cierre  else None,
        "proximo_venc":    str(proximo_venc)      if proximo_venc    else None,
    }
    count = insert_gastos(records, import_info=import_info)

    # ── Deduplicar contra gastos ya importados por el scraper ─────────────────
    # Si el scraper ya auto-importó transacciones del período que acaba de cerrarse,
    # el PDF recién subido genera duplicados. Eliminamos la versión del scraper
    # (el PDF es el resumen oficial) y actualizamos los movimientos_raw a 'matched'.
    _SCRAPER_PARSERS = frozenset({"amex", "bbva_mc", "bbva_visa"})
    deduped = 0
    if fuente in _SCRAPER_PARSERS:
        from scrapers_db import consolidate_scraper_duplicates
        deduped = consolidate_scraper_duplicates(effective_fuente, records)
        if deduped:
            logger.info("[upload] %s: %d duplicado(s) de scraper consolidados.",
                        effective_fuente, deduped)

    # Auto-update balance if the parser detected one
    saldo = getattr(PARSERS[fuente], "saldo_final", None)
    if saldo is not None:
        upsert_cuenta_saldo(effective_fuente, float(saldo))

    result: dict = {"importados": count, "total_parseados": len(gastos)}
    if ajuste_ars is not None:
        result["ajuste_resumen_ars"] = ajuste_ars
    if deduped:
        result["scraper_duplicados_eliminados"] = deduped
    return result


def _preview_upload_reconcile(records: list[dict], effective_fuente: str) -> dict:
    """
    Dry-run reconciliation: matches parsed PDF/XLS records against movimientos_raw
    and existing gastos. Does NOT modify the database.

    Returns per-record status and orphan scraper gastos in the period.
    """
    import sqlite3
    from datetime import datetime, timedelta
    from userctx import get_db_path
    from conciliacion import _score, DATE_WINDOW_DAYS, AUTO_MATCH_THRESHOLD

    empty_summary = {
        "total_pdf": len(records),
        "already_imported": 0,
        "raw_match_high": 0,
        "raw_match_low": 0,
        "new": 0,
        "scraper_orphans": 0,
        "skip_modal": True,
    }
    if not records:
        return {"fuente": effective_fuente, "periodo": None,
                "pdf_records": [], "scraper_orphans": [], "summary": empty_summary}

    fechas = [str(r.get("fecha", ""))[:10] for r in records if r.get("fecha")]
    if not fechas:
        return {"fuente": effective_fuente, "periodo": None,
                "pdf_records": [], "scraper_orphans": [], "summary": empty_summary}

    periodo_desde = min(fechas)
    periodo_hasta = max(fechas)
    d_from = (datetime.fromisoformat(periodo_desde) - timedelta(days=DATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    d_to   = (datetime.fromisoformat(periodo_hasta) + timedelta(days=DATE_WINDOW_DAYS)).strftime("%Y-%m-%d")

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        raws = [dict(r) for r in conn.execute(
            """SELECT id, fecha, descripcion, monto, moneda, estado
               FROM movimientos_raw
               WHERE fuente=? AND fecha BETWEEN ? AND ? AND estado NOT IN ('ignored')""",
            (effective_fuente, d_from, d_to),
        ).fetchall()]
        gastos_db = [dict(g) for g in conn.execute(
            """SELECT id, fecha, descripcion, monto, moneda, archivo_origen, categoria
               FROM gastos WHERE fuente=? AND fecha BETWEEN ? AND ?""",
            (effective_fuente, d_from, d_to),
        ).fetchall()]
    finally:
        conn.close()

    gastos_scraper = [g for g in gastos_db if g.get("archivo_origen") == "scraper"]
    gastos_prev    = [g for g in gastos_db
                      if g.get("archivo_origen") not in (None, "scraper", "manual")]
    has_raws       = bool(raws)

    used_raw_ids = set()
    counts = {"already_imported": 0, "raw_match_high": 0, "raw_match_low": 0, "new": 0}
    pdf_out = []

    for idx, record in enumerate(records):
        r_fecha  = str(record.get("fecha", ""))[:10]
        r_desc   = record.get("descripcion", "")
        r_monto  = float(record.get("monto", 0))
        r_moneda = record.get("moneda", "ARS")
        rec = {"fecha": r_fecha, "descripcion": r_desc, "monto": r_monto, "moneda": r_moneda}

        entry = {
            "idx": idx,
            "fecha": r_fecha,
            "descripcion": r_desc,
            "monto": r_monto,
            "moneda": r_moneda,
            "status": "new",
            "match_raw": None,
            "match_gasto": None,
        }

        # 1. Check duplicate in previously-imported (non-scraper) gastos
        best_prev_score = 0.0
        best_prev = None
        for g in gastos_prev:
            if g["moneda"] != r_moneda:
                continue
            if abs(float(g["monto"]) - abs(r_monto)) > 0.02:
                continue
            s = _score(rec, g)
            if s > best_prev_score:
                best_prev_score = s
                best_prev = g

        if best_prev and best_prev_score >= AUTO_MATCH_THRESHOLD:
            entry["status"] = "already_imported"
            entry["match_gasto"] = {
                "id": best_prev["id"],
                "fecha": best_prev["fecha"],
                "descripcion": best_prev["descripcion"],
                "monto": float(best_prev["monto"]),
                "moneda": best_prev["moneda"],
                "archivo_origen": best_prev.get("archivo_origen"),
                "confianza": round(best_prev_score, 3),
            }
            counts["already_imported"] += 1
            pdf_out.append(entry)
            continue

        # 2. Match against movimientos_raw (greedy: track used IDs)
        candidates = [
            r for r in raws
            if r["id"] not in used_raw_ids
               and r["moneda"] == r_moneda
               and abs(float(r["monto"]) - abs(r_monto)) < 0.02
        ]
        best_raw_score = 0.0
        best_raw = None
        for r in candidates:
            s = _score(rec, r)
            if s > best_raw_score:
                best_raw_score = s
                best_raw = r

        if best_raw and best_raw_score > 0.4:
            used_raw_ids.add(best_raw["id"])
            entry["match_raw"] = {
                "id": best_raw["id"],
                "fecha": best_raw["fecha"],
                "descripcion": best_raw["descripcion"],
                "monto": float(best_raw["monto"]),
                "moneda": best_raw["moneda"],
                "estado": best_raw.get("estado"),
                "confianza": round(best_raw_score, 3),
            }
            if best_raw_score >= AUTO_MATCH_THRESHOLD:
                entry["status"] = "raw_match_high"
                counts["raw_match_high"] += 1
            else:
                entry["status"] = "raw_match_low"
                counts["raw_match_low"] += 1
        else:
            entry["status"] = "new"
            counts["new"] += 1

        pdf_out.append(entry)

    # Orphan scraper gastos: in the exact statement period, not matched by any PDF record
    orphans = []
    for g in gastos_scraper:
        if g["fecha"] < periodo_desde or g["fecha"] > periodo_hasta:
            continue
        g_monto  = float(g["monto"])
        g_moneda = g["moneda"]
        best = 0.0
        for record in records:
            if record.get("moneda", "ARS") != g_moneda:
                continue
            if abs(float(record.get("monto", 0)) - abs(g_monto)) > 0.02:
                continue
            s = _score(
                {"fecha": str(record.get("fecha", ""))[:10], "descripcion": record.get("descripcion", "")},
                g,
            )
            if s > best:
                best = s
        if best < AUTO_MATCH_THRESHOLD:
            orphans.append({
                "id": g["id"],
                "fecha": g["fecha"],
                "descripcion": g["descripcion"],
                "monto": g_monto,
                "moneda": g_moneda,
                "categoria": g.get("categoria"),
            })

    # Show modal only when there's something worth reviewing
    skip_modal = (
        counts["already_imported"] == 0
        and counts["raw_match_low"] == 0
        and len(orphans) == 0
        and (not has_raws or counts["new"] == 0)
    )

    return {
        "fuente": effective_fuente,
        "periodo": {"desde": periodo_desde, "hasta": periodo_hasta},
        "pdf_records": pdf_out,
        "scraper_orphans": orphans,
        "summary": {
            "total_pdf": len(records),
            "already_imported": counts["already_imported"],
            "raw_match_high": counts["raw_match_high"],
            "raw_match_low": counts["raw_match_low"],
            "new": counts["new"],
            "scraper_orphans": len(orphans),
            "skip_modal": skip_modal,
        },
    }

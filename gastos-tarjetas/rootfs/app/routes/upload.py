import io
from collections import Counter

from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException

from auth import require_auth
from categorizer import categorize
from db import insert_gastos, upsert_cuenta_saldo, _CC_FUENTES
from parsers import PARSERS
from user_config import read_user_config

router = APIRouter()


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    fuente: str = Form(...),
    include_rg5617_credits: str = Form("false"),
):
    require_auth(request)

    if fuente not in PARSERS:
        raise HTTPException(400, f"Fuente desconocida: {fuente}. Opciones: {list(PARSERS)}")

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
        cat, fuente_cat = await categorize(g.descripcion)
        d = g.model_dump()
        d["categoria"] = cat
        d["categoria_fuente"] = fuente_cat
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
                "fuente":          fuente,
                "categoria":       "Créditos tarjeta",
                "categoria_fuente": "auto",
                "archivo_origen":  file.filename or fuente,
                "usuario":         usuario_default,
            })
            ajuste_ars = delta

    import_info = {
        "fuente":          fuente,
        "archivo":         file.filename or fuente,
        "mes_resumen":     mes_resumen,
        "fecha_venc":      str(fecha_venc)       if fecha_venc      else None,
        "total_ars":       float(stmt_ars)        if stmt_ars        else None,
        "total_usd":       float(stmt_usd)        if stmt_usd        else None,
        "proximo_cierre":  str(proximo_cierre)    if proximo_cierre  else None,
        "proximo_venc":    str(proximo_venc)      if proximo_venc    else None,
    }
    count = insert_gastos(records, import_info=import_info)

    # Auto-update balance if the parser detected one
    saldo = getattr(PARSERS[fuente], "saldo_final", None)
    if saldo is not None:
        upsert_cuenta_saldo(fuente, float(saldo))

    result: dict = {"importados": count, "total_parseados": len(gastos)}
    if ajuste_ars is not None:
        result["ajuste_resumen_ars"] = ajuste_ars
    return result

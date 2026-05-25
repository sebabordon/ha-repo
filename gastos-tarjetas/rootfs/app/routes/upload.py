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

    fecha_venc  = getattr(PARSERS[fuente], "fecha_vencimiento", None)
    stmt_ars    = getattr(PARSERS[fuente], "stmt_total_ars",    None)
    stmt_usd    = getattr(PARSERS[fuente], "stmt_total_usd",    None)

    # ── Synthetic "Créditos del resumen" adjustment ─────────────────────────────
    # When the parser detected the statement's TOTAL A PAGAR / SALDO ACTUAL,
    # insert a balancing row so that sum(all ARS transactions for this import)
    # equals the statement total.  The delta is almost always negative (a credit),
    # meaning the card charged LESS than the raw sum of egresos — e.g. because a
    # previous overpayment was applied.  A positive delta means the PDF total
    # exceeds the sum of parsed transactions (parser missed something).
    ajuste_ars: float | None = None
    if stmt_ars is not None:
        ars_egresos = sum(
            float(r["monto"]) for r in records
            if r.get("moneda") == "ARS" and float(r["monto"]) > 0
        )
        delta = round(float(stmt_ars) - ars_egresos, 2)
        if abs(delta) > 0.01:
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
        "fuente":      fuente,
        "archivo":     file.filename or fuente,
        "mes_resumen": mes_resumen,
        "fecha_venc":  str(fecha_venc)    if fecha_venc else None,
        "total_ars":   float(stmt_ars)    if stmt_ars   else None,
        "total_usd":   float(stmt_usd)    if stmt_usd   else None,
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

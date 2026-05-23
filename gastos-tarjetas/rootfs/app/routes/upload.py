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

    user_cfg       = read_user_config()
    usuario_default = user_cfg["fuente_usuario"].get(fuente)
    reglas_usuario  = user_cfg.get("reglas_usuario", [])

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
            # Parser detected a specific person (e.g. additional cardholder)
            d["usuario"] = g.usuario
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

    import_info = {
        "fuente":       fuente,
        "archivo":      file.filename or fuente,
        "mes_resumen":  mes_resumen,
    }
    count = insert_gastos(records, import_info=import_info)

    # Auto-update balance if the parser detected one
    saldo = getattr(PARSERS[fuente], "saldo_final", None)
    if saldo is not None:
        upsert_cuenta_saldo(fuente, float(saldo))

    return {"importados": count, "total_parseados": len(gastos)}

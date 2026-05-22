import io
from collections import Counter

from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException

from auth import require_auth
from categorizer import categorize
from db import insert_gastos, upsert_cuenta_saldo
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

    usuario_default = read_user_config()["fuente_usuario"].get(fuente)
    records = []
    for g in gastos:
        cat, fuente_cat = await categorize(g.descripcion)
        d = g.model_dump()
        d["categoria"] = cat
        d["categoria_fuente"] = fuente_cat
        d["usuario"] = g.usuario if g.usuario is not None else usuario_default
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

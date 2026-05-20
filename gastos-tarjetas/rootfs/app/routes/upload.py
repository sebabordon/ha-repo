import io

from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException

from auth import require_auth
from categorizer import categorize
from db import insert_gastos, upsert_cuenta_saldo
from parsers import PARSERS

router = APIRouter()

# Default user assignment by source (used when parser doesn't set usuario)
_USUARIO_FUENTE = {
    "amex": "Seba",
    "bbva_mc": "Seba",
    "bbva_visa": "Seba",
    "bbva_cuenta": "Seba",
    "mercadopago": "Seba",
}


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

    usuario_default = _USUARIO_FUENTE.get(fuente)
    records = []
    for g in gastos:
        cat, fuente_cat = await categorize(g.descripcion)
        d = g.model_dump()
        d["categoria"] = cat
        d["categoria_fuente"] = fuente_cat
        d["usuario"] = g.usuario if g.usuario is not None else usuario_default
        records.append(d)

    count = insert_gastos(records)

    # Auto-update balance if the parser detected one
    saldo = getattr(PARSERS[fuente], "saldo_final", None)
    if saldo is not None:
        upsert_cuenta_saldo(fuente, float(saldo))

    return {"importados": count, "total_parseados": len(gastos)}

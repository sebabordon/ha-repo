from typing import Optional
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from auth import require_auth
from db import (
    get_cuentas, update_cuenta, rename_cuenta,
    create_cuenta_manual, create_cuenta_auto, delete_cuenta_manual,
    delete_cuenta_any, count_gastos_cuenta, update_cuenta_parser,
    get_movimientos_cuenta, insert_movimiento_manual, delete_movimiento_manual,
    split_iol_multi_to_ars, reorder_cuentas,
)

router = APIRouter()


@router.get("/cuentas")
def list_cuentas(request: Request):
    require_auth(request)
    return get_cuentas()


@router.post("/cuentas/reorder")
def post_reorder_cuentas(body: dict, request: Request):
    """
    Reordena las cuentas. Body: {"fuentes": ["fuente1","fuente2", ...]} en el
    orden deseado (primera = arriba). Se refleja en el tab, los chips y los combos.
    """
    require_auth(request)
    fuentes = body.get("fuentes")
    if not isinstance(fuentes, list) or not all(isinstance(f, str) for f in fuentes):
        raise HTTPException(400, "fuentes debe ser una lista de strings")
    reorder_cuentas(fuentes)
    return {"ok": True, "cuentas": get_cuentas()}


@router.post("/cuentas")
async def post_cuenta(body: dict, request: Request):
    """
    Crea una cuenta nueva.
    Body:
      - nombre (requerido)
      - moneda: "ARS" | "USD" (default "ARS")
      - tipo:   "manual" (default) | "auto"
      - Si tipo="auto":
          - scraper_instance_id (int, opcional) → linkea a una instancia existente
          - scraper_product_key (str, opcional, default "main")
    """
    require_auth(request)
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(400, "nombre requerido")
    moneda = body.get("moneda", "ARS")
    if moneda not in ("ARS", "USD"):
        moneda = "ARS"

    tipo = (body.get("tipo") or "manual").strip().lower()
    if tipo == "auto":
        inst_id_raw = body.get("scraper_instance_id")
        try:
            inst_id = int(inst_id_raw) if inst_id_raw not in (None, "", 0, "0") else None
        except (ValueError, TypeError):
            raise HTTPException(400, "scraper_instance_id inválido")
        product_key = (body.get("scraper_product_key") or "main").strip() or "main"
        # Si linkeás a una instancia BBVA, validar que product_key esté en ARS/USD/EUR
        if inst_id is not None:
            from scraper_instances_db import get_instance
            inst = get_instance(inst_id)
            if not inst:
                raise HTTPException(404, f"Instancia {inst_id} no encontrada")
            if inst["banco"] == "bbva" and product_key.upper() not in ("ARS", "USD", "EUR"):
                product_key = "ARS"
            # IOL separa cuentas por moneda: el product_key ES la moneda.
            if inst["banco"] == "invertironline":
                product_key = moneda.upper()
        new = create_cuenta_auto(nombre, moneda, inst_id, product_key)
        # Al crear la cuenta USD de IOL, migrar la cuenta MULTI preexistente a ARS
        # pura (su saldo USD pasa a vivir en la cuenta nueva).
        if inst_id is not None and inst and inst["banco"] == "invertironline" and moneda == "USD":
            split_iol_multi_to_ars(inst_id)
        # Si linkeamos a una instancia, reload del scheduler para captar la nueva cuenta
        if inst_id is not None:
            try:
                from scraper_scheduler import reload_scheduler
                reload_scheduler()
            except Exception:
                pass
        return new

    return create_cuenta_manual(nombre, moneda)


@router.put("/cuentas/{fuente}")
def put_cuenta(fuente: str, body: dict, request: Request):
    require_auth(request)
    current = next((c for c in get_cuentas() if c["fuente"] == fuente), None)
    if not current:
        raise HTTPException(404, f"Cuenta {fuente} no encontrada")
    if "nombre" in body:
        nuevo_nombre = str(body["nombre"]).strip()
        if nuevo_nombre:
            rename_cuenta(fuente, nuevo_nombre)
    moneda = body.get("moneda", current["moneda"])
    if moneda not in ("ARS", "USD", "MULTI"):
        moneda = current["moneda"]
    update_cuenta(
        fuente=fuente,
        saldo=float(body.get("saldo", current["saldo"])),
        saldo_usd=float(body.get("saldo_usd", current.get("saldo_usd", 0))),
        moneda=moneda,
        activa=int(body.get("activa", current["activa"])),
        auto_saldo=int(body.get("auto_saldo", current["auto_saldo"])),
        cuenta_tipo=str(body.get("cuenta_tipo", current.get("cuenta_tipo", "bank"))),
    )
    return {"ok": True}


@router.delete("/cuentas/{fuente}")
async def del_cuenta(fuente: str, request: Request,
                     delete_gastos: bool = True):
    """
    Borra una cuenta (manual o auto).  Por defecto borra también los gastos y
    `movimientos_raw` asociados.  Si `delete_gastos=false`, los gastos quedan
    huérfanos (sin cuenta) — útil si querés mantener el historial.
    Si la cuenta estaba linkeada a una scraper_instance, la instancia NO se
    borra (otras cuentas podrían estar usándola).
    """
    require_auth(request)
    result = delete_cuenta_any(fuente, delete_gastos=delete_gastos)
    if not result["deleted"]:
        raise HTTPException(404, f"Cuenta '{fuente}' no encontrada")
    # Si era auto y tenía instancia linkeada, recargar scheduler para que sepa
    try:
        from scraper_scheduler import reload_scheduler
        reload_scheduler()
    except Exception:
        pass
    return {"ok": True, **result}


@router.get("/cuentas/{fuente}/gastos-count")
def get_cuenta_gastos_count(fuente: str, request: Request):
    """Cantidad de gastos asociados — usado para mostrar warning antes de borrar."""
    require_auth(request)
    return {"fuente": fuente, "gastos": count_gastos_cuenta(fuente)}


@router.put("/cuentas/{fuente}/parser")
def put_cuenta_parser(fuente: str, body: dict, request: Request):
    """
    Asigna/desasigna el `parser_type` de una cuenta.
    Body: { parser_type: str|null }  — null/"" desasigna.
    """
    require_auth(request)
    parser_type = (body.get("parser_type") or "").strip() or None
    if parser_type:
        try:
            from parsers import PARSERS
            if parser_type not in PARSERS:
                raise HTTPException(400, f"parser_type desconocido: {parser_type!r}. "
                                         f"Opciones: {list(PARSERS)}")
        except ImportError:
            pass   # no validamos si parsers no se puede importar
    if not update_cuenta_parser(fuente, parser_type):
        raise HTTPException(404, f"Cuenta '{fuente}' no encontrada")
    return {"ok": True, "fuente": fuente, "parser_type": parser_type}


@router.get("/parsers")
def list_parsers(request: Request):
    """
    Lista los parsers disponibles para asignar a una cuenta.
    Devuelve [{key, label, sub, accept}].
    """
    require_auth(request)
    return [
        {"key": "amex",        "label": "AMEX",         "sub": "PDF",  "accept": ".pdf"},
        {"key": "bbva_mc",     "label": "BBVA MC",      "sub": "PDF",  "accept": ".pdf"},
        {"key": "bbva_visa",   "label": "BBVA Visa",    "sub": "PDF",  "accept": ".pdf"},
        {"key": "bbva_cuenta", "label": "BBVA Cuenta",  "sub": "PDF",  "accept": ".pdf"},
        {"key": "galicia_mc",  "label": "Galicia MC",   "sub": "PDF",  "accept": ".pdf"},
        {"key": "mercadopago", "label": "MercadoPago",  "sub": "XLSX", "accept": ".xls,.xlsx"},
    ]


@router.post("/cuentas/{fuente}/upload/preview")
async def preview_cuenta_upload(
    fuente: str,
    request: Request,
    file: UploadFile = File(...),
    include_rg5617_credits: str = Form("false"),
):
    """
    Dry-run reconciliation preview: parses the file WITHOUT inserting into DB.
    Returns per-record match status vs movimientos_raw / existing gastos.
    """
    require_auth(request)
    import io
    from parsers import PARSERS
    from db import _CC_FUENTES
    from routes.upload import _preview_upload_reconcile

    cuentas = get_cuentas()
    cuenta = next((c for c in cuentas if c["fuente"] == fuente), None)
    if not cuenta:
        raise HTTPException(404, f"Cuenta '{fuente}' no encontrada")

    parser_type      = cuenta.get("parser_type") or fuente
    effective_fuente = fuente

    if parser_type not in PARSERS:
        raise HTTPException(400, f"Parser desconocido: {parser_type}")

    content = await file.read()
    try:
        gastos = PARSERS[parser_type].parse(io.BytesIO(content), file.filename)
    except Exception as e:
        raise HTTPException(422, f"Error al parsear archivo: {e}")

    if not gastos:
        return {
            "fuente": effective_fuente, "periodo": None,
            "pdf_records": [], "scraper_orphans": [],
            "summary": {"total_pdf": 0, "already_imported": 0, "raw_match_high": 0,
                        "raw_match_low": 0, "new": 0, "scraper_orphans": 0, "skip_modal": True},
        }

    if include_rg5617_credits.lower() not in ("true", "1", "yes"):
        gastos = [g for g in gastos if not ("5617" in g.descripcion and g.monto < 0)]

    needs_flip = parser_type not in _CC_FUENTES
    records = []
    for g in gastos:
        d = g.model_dump()
        d["fuente"] = effective_fuente
        d["monto"] = -float(d["monto"]) if (needs_flip and d["monto"] != 0) else float(d["monto"])
        records.append(d)

    return _preview_upload_reconcile(records, effective_fuente)


@router.post("/cuentas/{fuente}/upload")
async def upload_cuenta(fuente: str, request: Request,
                        file: UploadFile = File(...),
                        include_rg5617_credits: str = Form("false")):
    """
    Upload de un PDF/XLSX para esta cuenta.  Usa el `parser_type` configurado
    en la cuenta (o cae al `fuente` si parser_type=NULL, para back-compat con
    las cuentas pre-existentes).
    """
    require_auth(request)
    # Determinar parser_type de la cuenta
    cuentas = get_cuentas()
    cuenta = next((c for c in cuentas if c["fuente"] == fuente), None)
    if not cuenta:
        raise HTTPException(404, f"Cuenta '{fuente}' no encontrada")
    parser_type = cuenta.get("parser_type") or fuente
    # Delegamos al handler de upload genérico — pero el `fuente` que se inserta
    # en gastos es el de la cuenta (NO el parser_type).  Importante para cuentas
    # con slug custom que comparten parser con un banco.
    from routes.upload import upload_file as legacy_upload
    return await legacy_upload(
        file=file, fuente=parser_type, request=request,
        include_rg5617_credits=include_rg5617_credits,
        target_fuente=fuente,
    )


@router.get("/cuentas/{fuente}/movimientos")
def get_movs(fuente: str, request: Request):
    require_auth(request)
    return get_movimientos_cuenta(fuente)


@router.post("/cuentas/{fuente}/movimientos")
def post_mov(fuente: str, body: dict, request: Request):
    require_auth(request)
    fecha       = (body.get("fecha") or "").strip()
    descripcion = (body.get("descripcion") or "").strip()
    monto_raw   = body.get("monto")
    moneda      = body.get("moneda", "ARS")
    categoria   = body.get("categoria") or None
    if not fecha or not descripcion or monto_raw is None:
        raise HTTPException(400, "fecha, descripcion y monto son requeridos")
    try:
        monto = float(str(monto_raw).replace(",", "."))
    except ValueError:
        raise HTTPException(400, "monto inválido")
    new_id = insert_movimiento_manual(fuente, fecha, descripcion, monto, moneda, categoria)
    return {"ok": True, "id": new_id}


@router.delete("/cuentas/{fuente}/movimientos/{mov_id}")
def del_mov(fuente: str, mov_id: int, request: Request):
    require_auth(request)
    if not delete_movimiento_manual(mov_id, fuente):
        raise HTTPException(404, "Movimiento no encontrado")
    return {"ok": True}

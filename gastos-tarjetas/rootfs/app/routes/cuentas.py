from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from auth import require_auth
from db import (
    get_cuentas, update_cuenta, rename_cuenta,
    create_cuenta_manual, create_cuenta_auto, delete_cuenta_manual,
    get_movimientos_cuenta, insert_movimiento_manual, delete_movimiento_manual,
)

router = APIRouter()


@router.get("/cuentas")
def list_cuentas(request: Request):
    require_auth(request)
    return get_cuentas()


@router.post("/cuentas")
def post_cuenta(body: dict, request: Request):
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
        new = create_cuenta_auto(nombre, moneda, inst_id, product_key)
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
    )
    return {"ok": True}


@router.delete("/cuentas/{fuente}")
def del_cuenta(fuente: str, request: Request):
    require_auth(request)
    if not delete_cuenta_manual(fuente):
        raise HTTPException(400, "Solo se pueden eliminar cuentas manuales")
    return {"ok": True}


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

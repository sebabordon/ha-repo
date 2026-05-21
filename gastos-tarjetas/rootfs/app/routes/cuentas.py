from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from auth import require_auth
from db import (
    get_cuentas, update_cuenta,
    create_cuenta_manual, delete_cuenta_manual,
    get_movimientos_cuenta, insert_movimiento_manual, delete_movimiento_manual,
)

router = APIRouter()


@router.get("/cuentas")
def list_cuentas(request: Request):
    require_auth(request)
    return get_cuentas()


@router.post("/cuentas")
def post_cuenta(body: dict, request: Request):
    require_auth(request)
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(400, "nombre requerido")
    moneda = body.get("moneda", "ARS")
    return create_cuenta_manual(nombre, moneda)


@router.put("/cuentas/{fuente}")
def put_cuenta(fuente: str, body: dict, request: Request):
    require_auth(request)
    current = next((c for c in get_cuentas() if c["fuente"] == fuente), None)
    if not current:
        raise HTTPException(404, f"Cuenta {fuente} no encontrada")
    update_cuenta(
        fuente=fuente,
        saldo=float(body.get("saldo", current["saldo"])),
        moneda=body.get("moneda", current["moneda"]),
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

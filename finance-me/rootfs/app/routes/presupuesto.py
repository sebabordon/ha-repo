from typing import Optional
from fastapi import APIRouter, Request, Query
from auth import require_auth
from db import (
    get_presupuestos, save_presupuestos, stats_presupuesto_vs_actual,
    get_presupuestos_usuario, save_presupuestos_usuario, stats_presupuesto_usuario_vs_actual,
)

router = APIRouter()


@router.get("/presupuesto")
def get_presupuesto(
    request: Request,
    mes: Optional[str] = Query(None),
):
    require_auth(request)
    items = get_presupuestos()
    if mes:
        vs_actual = stats_presupuesto_vs_actual(mes)
        return {"items": items, "vs_actual": vs_actual}
    return {"items": items, "vs_actual": []}


@router.put("/presupuesto")
def put_presupuesto(body: dict, request: Request):
    require_auth(request)
    items = body.get("items", [])
    save_presupuestos(items)
    return {"ok": True, "guardados": len(items)}


@router.get("/presupuesto/usuario")
def get_presupuesto_usuario(
    request: Request,
    mes: Optional[str] = Query(None),
):
    require_auth(request)
    items = get_presupuestos_usuario()
    if mes:
        vs_actual = stats_presupuesto_usuario_vs_actual(mes)
        return {"items": items, "vs_actual": vs_actual}
    return {"items": items, "vs_actual": []}


@router.put("/presupuesto/usuario")
def put_presupuesto_usuario(body: dict, request: Request):
    require_auth(request)
    items = body.get("items", [])
    save_presupuestos_usuario(items)
    return {"ok": True, "guardados": len(items)}

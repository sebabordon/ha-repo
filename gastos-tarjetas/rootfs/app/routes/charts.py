from typing import Optional
from fastapi import APIRouter, Request, Query
from auth import require_auth
from db import (
    get_chart_layout, save_chart_layout,
    get_custom_charts, create_custom_chart, update_custom_chart, delete_custom_chart,
    stats_pivot,
)

router = APIRouter()


@router.get("/charts/layout")
def get_layout(request: Request):
    require_auth(request)
    return {"layout": get_chart_layout(), "custom": get_custom_charts()}


@router.put("/charts/layout")
def put_layout(body: dict, request: Request):
    require_auth(request)
    save_chart_layout(body.get("layout", []))
    return {"ok": True}


@router.get("/charts/custom")
def list_custom(request: Request):
    require_auth(request)
    return get_custom_charts()


@router.post("/charts/custom")
def post_custom(body: dict, request: Request):
    require_auth(request)
    new_id = create_custom_chart(body)
    return {"id": new_id}


@router.put("/charts/custom/{id}")
def put_custom(id: int, body: dict, request: Request):
    require_auth(request)
    update_custom_chart(id, body)
    return {"ok": True}


@router.delete("/charts/custom/{id}")
def del_custom(id: int, request: Request):
    require_auth(request)
    delete_custom_chart(id)
    return {"ok": True}


@router.get("/stats/pivot")
def get_pivot(
    request: Request,
    dimension:          str           = Query("categoria"),
    metrica:            str           = Query("egresos"),
    fuente:             Optional[str] = Query(None),
    usuario:            Optional[str] = Query(None),
    mes:                Optional[str] = Query(None),
    meses:              int           = Query(6),
    moneda:             str           = Query("ARS"),
    excluir_especiales: bool          = Query(True),
    categoria:          Optional[str] = Query(None),
):
    require_auth(request)
    return {"data": stats_pivot(
        dimension=dimension, metrica=metrica,
        fuente=fuente, usuario=usuario, mes=mes, meses=meses,
        moneda=moneda, excluir_especiales=excluir_especiales, categoria=categoria,
    )}

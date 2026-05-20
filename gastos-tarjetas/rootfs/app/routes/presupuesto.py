from typing import Optional
from fastapi import APIRouter, Request, Query
from auth import require_auth
from db import get_presupuestos, save_presupuestos, stats_presupuesto_vs_actual

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

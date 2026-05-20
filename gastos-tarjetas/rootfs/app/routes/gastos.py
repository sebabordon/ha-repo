from fastapi import APIRouter, Request, Query
from typing import Optional
from auth import require_auth
from db import list_gastos, update_categoria

router = APIRouter()


@router.get("/gastos")
def get_gastos(
    request: Request,
    fuente: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
):
    require_auth(request)
    return list_gastos(fuente=fuente, categoria=categoria)


@router.patch("/gastos/{gasto_id}/categoria")
def patch_categoria(gasto_id: int, body: dict, request: Request):
    require_auth(request)
    categoria = body.get("categoria", "")
    update_categoria(gasto_id, categoria)
    return {"ok": True}

from fastapi import APIRouter, Request
from auth import require_auth
from db import get_categorias_flat, save_categorias

router = APIRouter()


@router.get("/categorias/managed")
def get_categorias_managed(request: Request):
    require_auth(request)
    return {"categorias": get_categorias_flat()}


@router.put("/categorias/managed")
def put_categorias_managed(body: dict, request: Request):
    require_auth(request)
    items = body.get("categorias", [])
    save_categorias(items)
    return {"ok": True, "guardadas": len(items)}

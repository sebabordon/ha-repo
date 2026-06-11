from fastapi import APIRouter, Request
from auth import require_auth
from db import get_categorias_flat, save_categorias, _get_categorias_children_map

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


@router.get("/categorias/hierarchy")
def get_categorias_hierarchy(request: Request):
    """Returns {parent_nombre: [child_nombre, ...]} for all categories with children."""
    require_auth(request)
    return _get_categorias_children_map()

from fastapi import APIRouter, Request
from auth import require_auth
from user_config import read_user_config, write_user_config

router = APIRouter()


@router.get("/config/usuarios")
def get_usuarios_config(request: Request):
    require_auth(request)
    return read_user_config()


@router.put("/config/usuarios")
def put_usuarios_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "usuarios" in body:
        usuarios = [str(u).strip() for u in body["usuarios"] if str(u).strip()]
        if usuarios:
            cfg["usuarios"] = usuarios
    if "fuente_usuario" in body:
        cfg["fuente_usuario"] = {str(k): str(v) for k, v in body["fuente_usuario"].items()}
    write_user_config(cfg)
    return {"ok": True}

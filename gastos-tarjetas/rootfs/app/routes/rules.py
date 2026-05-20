import yaml
from fastapi import APIRouter, Request, HTTPException
from auth import require_auth
from config import RULES_FILE
from models import ReglasCategorias

router = APIRouter()


@router.get("/rules")
def get_rules(request: Request):
    require_auth(request)
    try:
        with open(RULES_FILE) as f:
            return yaml.safe_load(f) or {"reglas": []}
    except FileNotFoundError:
        return {"reglas": []}
    except yaml.YAMLError:
        return {"reglas": [], "error": "rules.yaml tiene un error de sintaxis — guardá las reglas para reemplazarlo."}


@router.put("/rules")
def put_rules(body: ReglasCategorias, request: Request):
    require_auth(request)
    try:
        with open(RULES_FILE, "w") as f:
            yaml.dump(body.model_dump(), f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        raise HTTPException(500, f"Error al guardar reglas: {e}")
    return {"ok": True}

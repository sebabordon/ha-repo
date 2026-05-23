import yaml
from fastapi import APIRouter, Request, HTTPException
from auth import require_auth
from categorizer import categorize_by_rules
from config import RULES_FILE, MATCH_RULES_FILE
from db import apply_rules_to_all, apply_match_rules, get_special_categorias
from models import ReglasCategorias, ReglasEmparejado

router = APIRouter()


@router.get("/categorias/especiales")
def get_categorias_especiales(request: Request):
    require_auth(request)
    return {"especiales": sorted(get_special_categorias())}


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


@router.post("/rules/apply")
def post_apply_rules(request: Request):
    """Re-apply all rules to every non-manually-categorized gasto."""
    require_auth(request)
    matched = apply_rules_to_all(categorize_by_rules)
    return {"ok": True, "categorizados": matched}


# ── Match / netting rules ────────────────────────────────────────────────────

def _load_match_rules() -> list[dict]:
    try:
        with open(MATCH_RULES_FILE) as f:
            data = yaml.safe_load(f) or {}
        return data.get("reglas", [])
    except FileNotFoundError:
        return []
    except yaml.YAMLError:
        return []


@router.get("/rules/match")
def get_match_rules(request: Request):
    require_auth(request)
    return {"reglas": _load_match_rules()}


@router.put("/rules/match")
def put_match_rules(body: ReglasEmparejado, request: Request):
    require_auth(request)
    try:
        with open(MATCH_RULES_FILE, "w") as f:
            yaml.dump(body.model_dump(), f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        raise HTTPException(500, f"Error al guardar reglas de emparejado: {e}")
    return {"ok": True}


@router.post("/rules/match/apply")
def post_apply_match_rules(request: Request):
    require_auth(request)
    rules = _load_match_rules()
    count = apply_match_rules(rules)
    return {"ok": True, "marcados": count}


@router.post("/rules/match/apply-one")
def post_apply_one_match_rule(body: dict, request: Request):
    require_auth(request)
    count = apply_match_rules([body])
    return {"ok": True, "marcados": count}

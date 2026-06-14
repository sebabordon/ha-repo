import yaml
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import Response
from auth import require_auth
from categorizer import categorize_by_rules, auto_add_keyword_to_rule, _invalidate_rules_cache
from userctx import get_rules_file, get_match_rules_file
from db import apply_rules_to_all, apply_match_rules, get_special_categorias, preview_rule_matches, apply_categoria_to_ids
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
        with open(get_rules_file()) as f:
            return yaml.safe_load(f) or {"reglas": []}
    except FileNotFoundError:
        return {"reglas": []}
    except yaml.YAMLError:
        return {"reglas": [], "error": "rules.yaml tiene un error de sintaxis — guardá las reglas para reemplazarlo."}


@router.put("/rules")
def put_rules(body: ReglasCategorias, request: Request):
    require_auth(request)
    try:
        with open(get_rules_file(), "w") as f:
            yaml.dump(body.model_dump(), f, allow_unicode=True, default_flow_style=False)
        _invalidate_rules_cache()
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
        with open(get_match_rules_file()) as f:
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
        with open(get_match_rules_file(), "w") as f:
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


# ── Learn / Export / Import ──────────────────────────────────────────────────

@router.post("/rules/learn")
def post_rules_learn(body: dict, request: Request):
    """Add a single keyword to the rule for a given category (user-confirmed)."""
    require_auth(request)
    keyword  = str(body.get("keyword",  "")).strip()
    categoria = str(body.get("categoria", "")).strip()
    if not keyword or not categoria:
        return {"ok": False}
    added = auto_add_keyword_to_rule(keyword, categoria)
    return {"ok": True, "agregado": added}


@router.get("/rules/suggest")
def get_rules_suggest(request: Request, desc: str = ""):
    """Return the category suggested by rules for a given description."""
    require_auth(request)
    cat = categorize_by_rules(desc.strip()) if desc.strip() else None
    return {"categoria": cat}


@router.get("/rules/export")
def get_rules_export(request: Request):
    require_auth(request)
    try:
        with open(get_rules_file()) as f:
            content = f.read()
    except FileNotFoundError:
        content = "reglas: []\n"
    return Response(
        content,
        media_type="text/yaml",
        headers={"Content-Disposition": "attachment; filename=rules.yaml"},
    )


@router.post("/rules/import")
async def post_rules_import(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    raw = await file.read()
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or "reglas" not in data:
            raise HTTPException(400, "El archivo no tiene el formato esperado (falta la clave 'reglas')")
        validated = ReglasCategorias(**data)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Error de sintaxis YAML: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Error al validar las reglas: {e}")
    with open(get_rules_file(), "w") as f:
        yaml.dump(validated.model_dump(), f, allow_unicode=True, default_flow_style=False)
    _invalidate_rules_cache()
    return {"ok": True, "reglas": len(validated.reglas)}


# ── Dry-run preview / apply selected ────────────────────────────────────────

@router.post("/rules/preview")
def post_rules_preview(body: dict, request: Request):
    """Return gastos that match a single rule, with current vs new category."""
    require_auth(request)
    regla           = body.get("regla", {})
    fecha_desde     = body.get("fecha_desde", "")
    fecha_hasta     = body.get("fecha_hasta", "")
    incluir_manuales = body.get("incluir_manuales", False)
    gastos = preview_rule_matches(regla, fecha_desde, fecha_hasta, incluir_manuales)
    return {"gastos": gastos}


@router.post("/rules/apply-selected")
def post_apply_selected(body: dict, request: Request):
    """Apply a category to a list of explicitly selected gasto IDs."""
    require_auth(request)
    ids       = [int(i) for i in body.get("ids", []) if str(i).isdigit()]
    categoria = str(body.get("categoria", "")).strip()
    if not ids or not categoria:
        return {"aplicados": 0}
    count = apply_categoria_to_ids(ids, categoria)
    return {"aplicados": count}

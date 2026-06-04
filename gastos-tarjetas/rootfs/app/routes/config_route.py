import yaml
from fastapi import APIRouter, Body, Request, HTTPException, UploadFile, File
from fastapi.responses import Response
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
    if "reglas_usuario" in body:
        reglas = []
        for r in body["reglas_usuario"]:
            palabras = [str(p).strip() for p in r.get("palabras", []) if str(p).strip()]
            usuario  = str(r.get("usuario", "")).strip()
            fuentes  = [str(f).strip() for f in r.get("fuentes", []) if str(f).strip()]
            if palabras and usuario:
                reglas.append({"palabras": palabras, "usuario": usuario, "fuentes": fuentes})
        cfg["reglas_usuario"] = reglas
    write_user_config(cfg)
    return {"ok": True}


@router.post("/config/usuarios/apply")
def apply_user_rules_endpoint(request: Request):
    require_auth(request)
    cfg     = read_user_config()
    reglas  = cfg.get("reglas_usuario", [])
    from db import apply_user_rules
    count = apply_user_rules(reglas)
    return {"asignados": count}


@router.get("/config/pwa-shortcuts")
def get_pwa_shortcuts(request: Request):
    require_auth(request)
    cfg = read_user_config()
    return cfg.get("pwa_shortcuts", [])


@router.put("/config/pwa-shortcuts")
def put_pwa_shortcuts(request: Request, body: list = Body(...)):
    require_auth(request)
    shortcuts = []
    for sc in body:
        fuente = str(sc.get("fuente", "")).strip()
        label  = str(sc.get("label", "")).strip()
        if fuente and label:
            shortcuts.append({"fuente": fuente, "label": label})
    cfg = read_user_config()
    cfg["pwa_shortcuts"] = shortcuts
    write_user_config(cfg)
    return {"ok": True}


@router.post("/config/usuarios/preview")
def preview_user_rule(body: dict, request: Request):
    """Dry-run: return gastos that would match a single user-assignment rule."""
    require_auth(request)
    from db import preview_user_rule_matches
    gastos = preview_user_rule_matches(
        regla=body.get("regla", {}),
        fecha_desde=body.get("fecha_desde", ""),
        fecha_hasta=body.get("fecha_hasta", ""),
    )
    return {"gastos": gastos}


@router.post("/config/usuarios/apply-selected")
def apply_usuario_selected(body: dict, request: Request):
    """Assign a person to a list of explicitly selected gasto IDs."""
    require_auth(request)
    from db import apply_usuario_to_ids
    ids     = [int(i) for i in body.get("ids", []) if str(i).isdigit()]
    usuario = str(body.get("usuario", "")).strip()
    if not ids or not usuario:
        return {"aplicados": 0}
    count = apply_usuario_to_ids(ids, usuario)
    return {"aplicados": count}


@router.get("/config/usuarios/rules/export")
def export_user_rules(request: Request):
    require_auth(request)
    cfg    = read_user_config()
    reglas = cfg.get("reglas_usuario", [])
    content = yaml.dump({"reglas": reglas}, allow_unicode=True, default_flow_style=False)
    return Response(
        content,
        media_type="text/yaml",
        headers={"Content-Disposition": "attachment; filename=user_rules.yaml"},
    )


@router.post("/config/usuarios/rules/import")
async def import_user_rules(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    raw = await file.read()
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or "reglas" not in data:
            raise HTTPException(400, "El archivo no tiene el formato esperado (falta la clave 'reglas')")
        reglas = []
        for r in data["reglas"]:
            palabras = [str(p).strip() for p in r.get("palabras", []) if str(p).strip()]
            usuario  = str(r.get("usuario", "")).strip()
            fuentes  = [str(f).strip() for f in r.get("fuentes", []) if str(f).strip()]
            if palabras and usuario:
                reglas.append({"palabras": palabras, "usuario": usuario, "fuentes": fuentes})
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Error de sintaxis YAML: {e}")
    cfg = read_user_config()
    cfg["reglas_usuario"] = reglas
    write_user_config(cfg)
    return {"ok": True, "reglas": len(reglas)}


@router.get("/config/dedup")
def get_dedup_config(request: Request):
    require_auth(request)
    from scrapers_db import _GENERIC_DESCS, _GENERIC_PREFIXES
    cfg = read_user_config()
    return {
        "dedup_prefijos": list(cfg.get("dedup_prefijos", list(_GENERIC_PREFIXES))),
        "dedup_exactos":  list(cfg.get("dedup_exactos",  sorted(_GENERIC_DESCS))),
    }


@router.put("/config/dedup")
def put_dedup_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "dedup_prefijos" in body:
        cfg["dedup_prefijos"] = [s.strip() for s in body["dedup_prefijos"] if str(s).strip()]
    if "dedup_exactos" in body:
        cfg["dedup_exactos"]  = [s.strip() for s in body["dedup_exactos"]  if str(s).strip()]
    write_user_config(cfg)
    return {"ok": True}


@router.post("/config/usuarios/rename-db")
def rename_usuario_in_db(body: dict, request: Request):
    """Rename a persona in all existing gastos rows (called after UI rename)."""
    require_auth(request)
    old_name = str(body.get("old", "")).strip()
    new_name = str(body.get("new", "")).strip()
    if not old_name or not new_name or old_name == new_name:
        return {"actualizados": 0}
    from db import rename_usuario_in_gastos
    count = rename_usuario_in_gastos(old_name, new_name)
    return {"actualizados": count}

import re
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


@router.get("/config/periodo")
def get_periodo_config(request: Request):
    require_auth(request)
    from db import periodo_actual
    cfg = read_user_config()
    return {
        "periodo_activo":      bool(cfg.get("periodo_activo", False)),
        "periodo_delta_dias":  int(cfg.get("periodo_delta_dias", 2) or 2),
        "periodo_overrides":   cfg.get("periodo_overrides", {}) or {},
        "periodo_actual":      periodo_actual(),
    }


@router.put("/config/periodo")
def put_periodo_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "periodo_activo" in body:
        cfg["periodo_activo"] = bool(body["periodo_activo"])
    if "periodo_delta_dias" in body:
        try:
            cfg["periodo_delta_dias"] = max(0, min(28, int(body["periodo_delta_dias"])))
        except (TypeError, ValueError):
            raise HTTPException(400, "periodo_delta_dias inválido (0..28)")
    if "periodo_overrides" in body:
        ovr: dict = {}
        for k, v in (body["periodo_overrides"] or {}).items():
            if not re.match(r"^\d{4}-\d{2}$", str(k)):
                continue
            try:
                ovr[str(k)] = max(0, min(28, int(v)))
            except (TypeError, ValueError):
                continue
        cfg["periodo_overrides"] = ovr
    write_user_config(cfg)
    return {"ok": True}


@router.get("/config/venc-match")
def get_venc_match_config(request: Request):
    require_auth(request)
    cfg = read_user_config()
    return {
        "venc_pago_match_activo":  bool(cfg.get("venc_pago_match_activo", True)),
        "venc_pago_match_dias":    int(cfg.get("venc_pago_match_dias", 8) or 8),
        "venc_pago_match_tol_ars": float(cfg.get("venc_pago_match_tol_ars", 5000.0) or 5000.0),
        "venc_pago_match_tol_usd": float(cfg.get("venc_pago_match_tol_usd", 1.0) or 1.0),
        "venc_pago_match_categorias": list(cfg.get("venc_pago_match_categorias", ["Pago de Tarjeta"])),
    }


@router.put("/config/venc-match")
def put_venc_match_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "venc_pago_match_activo" in body:
        cfg["venc_pago_match_activo"] = bool(body["venc_pago_match_activo"])
    if "venc_pago_match_dias" in body:
        try:
            cfg["venc_pago_match_dias"] = max(0, min(60, int(body["venc_pago_match_dias"])))
        except (TypeError, ValueError):
            raise HTTPException(400, "venc_pago_match_dias inválido (0..60)")
    if "venc_pago_match_tol_ars" in body:
        try:
            cfg["venc_pago_match_tol_ars"] = max(0.0, float(body["venc_pago_match_tol_ars"]))
        except (TypeError, ValueError):
            raise HTTPException(400, "venc_pago_match_tol_ars inválido")
    if "venc_pago_match_tol_usd" in body:
        try:
            cfg["venc_pago_match_tol_usd"] = max(0.0, float(body["venc_pago_match_tol_usd"]))
        except (TypeError, ValueError):
            raise HTTPException(400, "venc_pago_match_tol_usd inválido")
    if "venc_pago_match_categorias" in body:
        cats = [str(c).strip() for c in (body["venc_pago_match_categorias"] or []) if str(c).strip()]
        cfg["venc_pago_match_categorias"] = cats or ["Pago de Tarjeta"]
    write_user_config(cfg)
    return {"ok": True}


# ── Categorización por IA (prompt + catálogo de categorías) ──────────────────

@router.get("/config/categorizacion")
def get_categorizacion_config(request: Request):
    require_auth(request)
    from user_config import config_default
    cfg = read_user_config()
    return {
        "categorizer_categorias": list(cfg.get("categorizer_categorias")
                                       or config_default("categorizer_categorias")),
        "categorizer_prompt": cfg.get("categorizer_prompt")
                              or config_default("categorizer_prompt"),
        "default_prompt": config_default("categorizer_prompt"),
    }


@router.put("/config/categorizacion")
def put_categorizacion_config(body: dict, request: Request):
    require_auth(request)
    from user_config import config_default
    cfg = read_user_config()
    if "categorizer_categorias" in body:
        cats = [str(c).strip() for c in (body["categorizer_categorias"] or []) if str(c).strip()]
        cfg["categorizer_categorias"] = cats or config_default("categorizer_categorias")
    if "categorizer_prompt" in body:
        prompt = str(body["categorizer_prompt"] or "").strip()
        # Validar que el template formatee bien con los placeholders disponibles.
        try:
            prompt.format(categorias="x", desc="y")
        except (KeyError, IndexError, ValueError):
            raise HTTPException(400, "El prompt tiene placeholders inválidos. "
                                     "Usá solo {categorias} y {desc}.")
        cfg["categorizer_prompt"] = prompt or config_default("categorizer_prompt")
    write_user_config(cfg)
    return {"ok": True}


# ── Categorías especiales fijas (excluidas de totales/gráficos) ──────────────

@router.get("/config/especiales")
def get_especiales_config(request: Request):
    require_auth(request)
    from user_config import config_default
    cfg = read_user_config()
    return {
        "categorias_especiales_builtin": list(
            cfg.get("categorias_especiales_builtin")
            or config_default("categorias_especiales_builtin")),
    }


@router.put("/config/especiales")
def put_especiales_config(body: dict, request: Request):
    require_auth(request)
    from user_config import config_default
    cfg = read_user_config()
    if "categorias_especiales_builtin" in body:
        names = [str(c).strip() for c in (body["categorias_especiales_builtin"] or []) if str(c).strip()]
        cfg["categorias_especiales_builtin"] = names or config_default("categorias_especiales_builtin")
    write_user_config(cfg)
    return {"ok": True}


# ── Paleta de íconos PWA por fuente ──────────────────────────────────────────

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@router.get("/config/iconos")
def get_iconos_config(request: Request):
    require_auth(request)
    from user_config import config_default
    cfg = read_user_config()
    return {
        "fuente_icon_styles": cfg.get("fuente_icon_styles")
                              or config_default("fuente_icon_styles"),
        "defaults": config_default("fuente_icon_styles"),
    }


@router.put("/config/iconos")
def put_iconos_config(request: Request, body: dict = Body(...)):
    require_auth(request)
    styles = body.get("fuente_icon_styles", body)
    clean: dict = {}
    for fuente, st in (styles or {}).items():
        if not isinstance(st, dict):
            continue
        bg = str(st.get("bg", "")).strip()
        fg = str(st.get("fg", "")).strip()
        lines = [str(l).strip() for l in (st.get("lines") or []) if str(l).strip()][:2]
        entry: dict = {}
        if _HEX_RE.match(bg): entry["bg"] = bg.upper()
        if _HEX_RE.match(fg): entry["fg"] = fg.upper()
        if lines:             entry["lines"] = lines
        if entry:
            clean[str(fuente).strip()] = entry
    cfg = read_user_config()
    cfg["fuente_icon_styles"] = clean
    write_user_config(cfg)
    return {"ok": True}


# ── Export / backup de la base de datos ──────────────────────────────────────

@router.get("/config/export-db")
def export_db(request: Request):
    """
    Exporta un snapshot consistente de la base del usuario actual.

    Usa `VACUUM INTO` (no copia el archivo crudo) para obtener una copia íntegra
    aunque la DB esté en modo WAL con escrituras en curso. Las credenciales
    cifradas de scrapers se borran del snapshot antes de descargarlo.
    """
    require_auth(request)
    import os
    import sqlite3
    import tempfile
    from datetime import datetime
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from userctx import get_db_path

    src = get_db_path()
    if not os.path.exists(src):
        raise HTTPException(404, "No hay base de datos para exportar todavía.")

    # VACUUM INTO requiere que el destino NO exista todavía.
    fd, tmp = tempfile.mkstemp(prefix="gastos_export_", suffix=".db")
    os.close(fd)
    os.unlink(tmp)

    src_conn = sqlite3.connect(src, timeout=10.0)
    try:
        src_conn.execute("PRAGMA busy_timeout=5000")
        src_conn.execute("VACUUM INTO ?", (tmp,))
    finally:
        src_conn.close()

    # Quitar credenciales cifradas del snapshot (no se exportan).
    exp = sqlite3.connect(tmp)
    try:
        exp.execute("UPDATE scraper_instances SET config='{}', config_encrypted=0")
        exp.commit()
    except sqlite3.OperationalError:
        pass  # tabla inexistente en bases viejas — nada que limpiar
    finally:
        exp.close()

    stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gastos_backup_{stamp}.db"
    return FileResponse(
        tmp,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(lambda: os.path.exists(tmp) and os.unlink(tmp)),
    )


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

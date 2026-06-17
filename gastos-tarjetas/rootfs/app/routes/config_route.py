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
    if "cardholder_usuario" in body:
        cfg["cardholder_usuario"] = {
            str(k): str(v).strip()
            for k, v in (body["cardholder_usuario"] or {}).items()
            if str(k).strip() and str(v).strip()
        }
    write_user_config(cfg)
    return {"ok": True}


@router.get("/config/cardholders")
def list_cardholders(request: Request):
    """
    Titulares de tarjeta distintos vistos en movimientos_raw (raw_data.cardholder),
    para poblar el mapeo cardholder → persona en la UI sin tipearlos a mano.
    """
    require_auth(request)
    from scrapers_db import list_cardholders as _list_cardholders
    return {"cardholders": _list_cardholders()}


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
    _pago_def = ["PAGO", "ACREDITAC", "AJUSTE", "PERCEPCION", "RG 5617"]
    return {
        "dedup_prefijos": list(cfg.get("dedup_prefijos", list(_GENERIC_PREFIXES))),
        "dedup_exactos":  list(cfg.get("dedup_exactos",  sorted(_GENERIC_DESCS))),
        "tarjeta_consumo_pago_patrones": list(cfg.get("tarjeta_consumo_pago_patrones", _pago_def)),
    }


@router.put("/config/dedup")
def put_dedup_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "dedup_prefijos" in body:
        cfg["dedup_prefijos"] = [s.strip() for s in body["dedup_prefijos"] if str(s).strip()]
    if "dedup_exactos" in body:
        cfg["dedup_exactos"]  = [s.strip() for s in body["dedup_exactos"]  if str(s).strip()]
    if "tarjeta_consumo_pago_patrones" in body:
        cfg["tarjeta_consumo_pago_patrones"] = [
            s.strip() for s in body["tarjeta_consumo_pago_patrones"] if str(s).strip()
        ]
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


@router.get("/config/venc-notif")
def get_venc_notif_config(request: Request):
    require_auth(request)
    cfg = read_user_config()
    return {
        "venc_notif_activo":     bool(cfg.get("venc_notif_activo", False)),
        "venc_notif_dias_antes": list(cfg.get("venc_notif_dias_antes", [3, 1])),
        "venc_notif_hora":       int(cfg.get("venc_notif_hora", 9) or 9),
    }


@router.put("/config/venc-notif")
def put_venc_notif_config(body: dict, request: Request):
    require_auth(request)
    cfg = read_user_config()
    if "venc_notif_activo" in body:
        cfg["venc_notif_activo"] = bool(body["venc_notif_activo"])
    if "venc_notif_dias_antes" in body:
        dias = []
        for x in (body["venc_notif_dias_antes"] or []):
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 60:
                dias.append(n)
        cfg["venc_notif_dias_antes"] = sorted(set(dias), reverse=True) or [3, 1]
    if "venc_notif_hora" in body:
        try:
            cfg["venc_notif_hora"] = max(0, min(23, int(body["venc_notif_hora"])))
        except (TypeError, ValueError):
            raise HTTPException(400, "venc_notif_hora inválido (0..23)")
    write_user_config(cfg)
    return {"ok": True}


@router.post("/config/venc-notif/test")
def test_venc_notif(request: Request):
    """Dispara el notifier de vencimientos AHORA (ignora hora/opt-in/dedup)."""
    require_auth(request)
    from vencimiento_notifier import notify_current_user
    sent = notify_current_user(force=True)
    return {"sent": sent}


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


# ── Export / backup / restore de los datos ───────────────────────────────────

# Archivos de config (fuera de la DB) que entran en el backup completo. Es una
# whitelist explícita: en el restore solo se extraen estos nombres (sin paths),
# evitando zip-slip.
_BACKUP_FILES = ("rules.yaml", "match_rules.yaml", "user_config.json")


def _snapshot_db_no_creds(src_db: str) -> str:
    """
    Devuelve la ruta a un snapshot temporal consistente de *src_db*.

    Usa `VACUUM INTO` (no copia el archivo crudo) para obtener una copia íntegra
    aunque la DB esté en modo WAL con escrituras en curso. Las credenciales
    cifradas de scrapers se vacían del snapshot. El llamador debe borrar el temp.
    """
    import os
    import sqlite3
    import tempfile

    # VACUUM INTO requiere que el destino NO exista todavía.
    fd, tmp = tempfile.mkstemp(prefix="gastos_snap_", suffix=".db")
    os.close(fd)
    os.unlink(tmp)

    src_conn = sqlite3.connect(src_db, timeout=10.0)
    try:
        src_conn.execute("PRAGMA busy_timeout=5000")
        src_conn.execute("VACUUM INTO ?", (tmp,))
    finally:
        src_conn.close()

    exp = sqlite3.connect(tmp)
    try:
        exp.execute("UPDATE scraper_instances SET config='{}', config_encrypted=0")
        exp.commit()
    except sqlite3.OperationalError:
        pass  # tabla inexistente en bases viejas — nada que limpiar
    finally:
        exp.close()
    return tmp


@router.get("/config/export-db")
def export_db(request: Request):
    """Descarga solo la base de datos (snapshot consistente, sin credenciales)."""
    require_auth(request)
    import os
    from datetime import datetime
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from userctx import get_db_path

    src = get_db_path()
    if not os.path.exists(src):
        raise HTTPException(404, "No hay base de datos para exportar todavía.")

    tmp = _snapshot_db_no_creds(src)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        tmp,
        media_type="application/octet-stream",
        filename=f"gastos_backup_{stamp}.db",
        background=BackgroundTask(lambda: os.path.exists(tmp) and os.unlink(tmp)),
    )


@router.get("/config/export-backup")
def export_backup(request: Request):
    """
    Descarga un backup completo (.zip): la base de datos (snapshot consistente,
    sin credenciales) más los archivos de config/reglas que viven fuera de la DB
    (rules.yaml, match_rules.yaml, user_config.json) y un manifest informativo.
    """
    require_auth(request)
    import os
    import json
    import tempfile
    import zipfile
    from datetime import datetime
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from userctx import get_data_dir, get_db_path
    from config import APP_VERSION

    data_dir = get_data_dir()
    src_db   = get_db_path()

    tmp_db = _snapshot_db_no_creds(src_db) if os.path.exists(src_db) else None

    fd, tmp_zip = tempfile.mkstemp(prefix="gastos_backup_", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            if tmp_db:
                z.write(tmp_db, "gastos.db")
            for fname in _BACKUP_FILES:
                p = os.path.join(data_dir, fname)
                if os.path.exists(p):
                    z.write(p, fname)
            manifest = {
                "app_version": APP_VERSION,
                "created_at":  datetime.now().isoformat(timespec="seconds"),
                "contents":    "gastos.db (sin credenciales de scrapers) + "
                               + ", ".join(_BACKUP_FILES),
            }
            z.writestr("backup_manifest.json",
                       json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        if tmp_db and os.path.exists(tmp_db):
            os.unlink(tmp_db)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        tmp_zip,
        media_type="application/zip",
        filename=f"gastos_backup_{stamp}.zip",
        background=BackgroundTask(lambda: os.path.exists(tmp_zip) and os.unlink(tmp_zip)),
    )


@router.post("/config/import-backup")
async def import_backup(request: Request, file: UploadFile = File(...)):
    """
    Restaura un backup completo (.zip) generado por /config/export-backup.

    REEMPLAZA la base de datos y los archivos de config del usuario actual.
    Valida que el .zip traiga un gastos.db SQLite íntegro antes de pisar nada.
    """
    require_auth(request)
    import os
    import io
    import sqlite3
    import zipfile
    from userctx import get_data_dir, get_db_path

    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "El archivo no es un .zip válido.")

    names = set(zf.namelist())
    if "gastos.db" not in names:
        raise HTTPException(400, "El backup no contiene gastos.db — ¿es un backup de Gastos?")

    db_bytes = zf.read("gastos.db")
    if not db_bytes.startswith(b"SQLite format 3\x00"):
        raise HTTPException(400, "El gastos.db del backup no es una base SQLite válida.")

    data_dir = get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    db_path = get_db_path()

    # 1. Escribir la DB a un temp en el mismo dir y validarla antes de reemplazar.
    tmp = db_path + ".restore_tmp"
    with open(tmp, "wb") as f:
        f.write(db_bytes)
    try:
        chk = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            row = chk.execute("PRAGMA integrity_check").fetchone()
        finally:
            chk.close()
        if not row or row[0] != "ok":
            raise HTTPException(400, "El gastos.db del backup falló el integrity_check.")
    except HTTPException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    except sqlite3.DatabaseError:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise HTTPException(400, "El gastos.db del backup no se pudo abrir.")

    # Borrar WAL/SHM viejos para que SQLite no los aplique sobre la DB nueva.
    for ext in ("-wal", "-shm"):
        p = db_path + ext
        if os.path.exists(p):
            try:
                os.unlink(p)
            except OSError:
                pass
    os.replace(tmp, db_path)
    restored = ["gastos.db"]

    # 2. Archivos de config (whitelist por basename, sin paths → sin zip-slip).
    for fname in _BACKUP_FILES:
        if fname in names:
            with open(os.path.join(data_dir, fname), "wb") as f:
                f.write(zf.read(fname))
            restored.append(fname)

    # 3. Re-migrar por si el backup viene de un esquema más viejo.
    from db import init_db
    init_db()

    return {"ok": True, "restaurados": restored}


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


# ── Tipo de cambio USD para presupuesto ──────────────────────────────────────

_TC_TIPOS_VALIDOS = {"tarjeta", "oficial", "blue"}


@router.get("/config/tc-dolar")
def get_tc_dolar_config(request: Request):
    require_auth(request)
    from user_config import config_default
    from tc import fetch_tc_dolar
    cfg  = read_user_config()
    tipo = cfg.get("tc_dolar_tipo") or config_default("tc_dolar_tipo") or "tarjeta"
    tc   = fetch_tc_dolar(tipo)
    return {"tipo": tipo, "tc": tc}


@router.put("/config/tc-dolar")
def put_tc_dolar_config(body: dict, request: Request):
    require_auth(request)
    tipo = str(body.get("tipo") or "tarjeta").strip().lower()
    if tipo not in _TC_TIPOS_VALIDOS:
        raise HTTPException(400, f"tipo inválido: {tipo}. Válidos: {sorted(_TC_TIPOS_VALIDOS)}")
    cfg = read_user_config()
    cfg["tc_dolar_tipo"] = tipo
    write_user_config(cfg)
    return {"ok": True, "tipo": tipo}

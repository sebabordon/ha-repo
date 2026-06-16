import io
import os
import re
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from html import escape

from fastapi import APIRouter, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from starlette.background import BackgroundTask

from auth import (
    get_registration_enabled, set_registration_enabled,
    list_users, delete_user, reset_password,
)
from config import DATA_DIR, APP_VERSION

router = APIRouter()

# Artefactos temporales / volátiles que NO entran en el backup completo: los
# -wal/-shm se pliegan dentro del snapshot VACUUM de cada .db, y los gastos_*
# son los propios temporales de export/import.
_BACKUP_SKIP_SUFFIXES = ("-wal", "-shm", ".restore_tmp", ".tmp")
_BACKUP_SKIP_PREFIXES = ("gastos_snap_", "gastos_backup_", "gastos_full_")
_SQLITE_MAGIC = b"SQLite format 3\x00"

_SAFE_PREFIX_RE = re.compile(r'^(/[a-zA-Z0-9_/-]*)?$')


def _safe_prefix(request: Request) -> str:
    prefix = request.headers.get("X-Ingress-Path", "")
    return prefix if _SAFE_PREFIX_RE.match(prefix) else ""


_STYLE = """
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       background:#f0f2f5;min-height:100vh;padding:2rem 1rem}
  .card{background:#fff;padding:2rem;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.1);
        max-width:600px;margin:0 auto}
  h2{margin-bottom:1.5rem;font-size:1.2rem;color:#16213e}
  h3{margin:1.5rem 0 .75rem;font-size:1rem;color:#16213e;border-bottom:1px solid #eee;padding-bottom:.4rem}
  .row{display:flex;align-items:center;justify-content:space-between;padding:.5rem 0;
       border-bottom:1px solid #f0f0f0}
  .row:last-child{border-bottom:none}
  .badge{display:inline-block;padding:.2rem .6rem;border-radius:12px;font-size:.8rem;font-weight:600}
  .badge-on{background:#d1fae5;color:#065f46}
  .badge-off{background:#fee2e2;color:#991b1b}
  .btn{padding:.5rem 1rem;border:none;border-radius:4px;font-size:.9rem;cursor:pointer;font-weight:500}
  .btn-primary{background:#16213e;color:#fff}
  .btn-primary:hover{background:#0f3460}
  .btn-danger{background:#ef4444;color:#fff}
  .btn-danger:hover{background:#dc2626}
  .btn-sm{padding:.3rem .7rem;font-size:.8rem}
  .back{display:inline-block;margin-bottom:1.5rem;color:#16213e;text-decoration:none;font-size:.9rem}
  .back:hover{text-decoration:underline}
  .empty{color:#aaa;font-size:.9rem;padding:.5rem 0}
  .hint{color:#666;font-size:.82rem;margin:.4rem 0;line-height:1.4}
  .hint code{background:#f0f0f0;padding:.05rem .3rem;border-radius:3px;font-size:.78rem}
  a.btn{text-decoration:none;display:inline-block}
  input[type=file]{font-size:.8rem;max-width:60%}
</style>
"""


def _require_admin(request: Request):
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        return None
    return user


def _redirect(request: Request, path: str, status_code: int = 303) -> RedirectResponse:
    prefix = _safe_prefix(request)
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)


# ── Backup / restore completo (todos los usuarios) ────────────────────────────

def _snapshot_full_db(src_db: str) -> str | None:
    """
    Snapshot consistente de una .db vía `VACUUM INTO` (íntegra aunque esté en WAL
    con escrituras en curso). A diferencia del export per-usuario, NO vacía las
    credenciales de scrapers: el backup completo se las lleva tal cual (cifradas).
    Devuelve la ruta temporal (a borrar por el llamador) o None si no es SQLite.
    """
    fd, tmp = tempfile.mkstemp(prefix="gastos_snap_", suffix=".db")
    os.close(fd)
    os.unlink(tmp)  # VACUUM INTO requiere que el destino no exista
    try:
        conn = sqlite3.connect(src_db, timeout=10.0)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("VACUUM INTO ?", (tmp,))
        finally:
            conn.close()
        return tmp
    except sqlite3.DatabaseError:
        if os.path.exists(tmp):
            os.unlink(tmp)
        return None


def _safe_target(base_abs: str, member: str) -> str | None:
    """
    Resuelve el destino de un miembro del zip dentro de *base_abs*, rechazando
    rutas absolutas y traversal (`..`). Devuelve la ruta absoluta segura o None.
    Defensa anti zip-slip: nunca se escribe fuera de DATA_DIR.
    """
    member = member.replace("\\", "/")
    if not member or member.startswith("/") or ".." in member.split("/"):
        return None
    target = os.path.abspath(os.path.join(base_abs, member))
    if target != base_abs and not target.startswith(base_abs + os.sep):
        return None
    return target


def _build_full_backup_zip(data_dir: str) -> str:
    """Arma un .zip con TODO /data (snapshot de cada .db + archivos crudos)."""
    fd, tmp_zip = tempfile.mkstemp(prefix="gastos_full_", suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(data_dir):
            for fn in files:
                if fn.endswith(_BACKUP_SKIP_SUFFIXES) or fn.startswith(_BACKUP_SKIP_PREFIXES):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, data_dir)
                if fn.endswith(".db"):
                    snap = _snapshot_full_db(full)
                    if snap:
                        try:
                            z.write(snap, rel)
                        finally:
                            if os.path.exists(snap):
                                os.unlink(snap)
                        continue
                    # snapshot falló (db corrupta/locked) → copia cruda como fallback
                try:
                    z.write(full, rel)
                except OSError:
                    pass  # archivo desaparecido entre walk y write — ignorar
        z.writestr("backup_manifest.json", json.dumps({
            "app_version": APP_VERSION,
            "created_at":  datetime.now().isoformat(timespec="seconds"),
            "type":        "full-admin",
            "contents":    "/data completo: users.json, settings, todas las DB de "
                           "usuario (con credenciales de scrapers cifradas), reglas y sesiones",
            "nota":        "Las credenciales de scrapers solo se descifran si la opción "
                           "scraper_encryption_key del add-on sigue siendo la misma.",
        }, ensure_ascii=False, indent=2))
    return tmp_zip


def _render_panel(request: Request, msg: str = "") -> HTMLResponse:
    prefix = _safe_prefix(request)
    reg = get_registration_enabled()
    users = list_users()

    badge = ('<span class="badge badge-on">ACTIVADO</span>' if reg
             else '<span class="badge badge-off">DESACTIVADO</span>')
    toggle_label = "Desactivar" if reg else "Activar"
    toggle_btn = f"""
        <form method="post" action="{prefix}/admin/registration" style="display:inline">
          <input type="hidden" name="enabled" value="{'false' if reg else 'true'}">
          <button class="btn btn-primary btn-sm" type="submit">{toggle_label}</button>
        </form>"""

    users_html = ""
    if users:
        rows = ""
        for email in users:
            safe_email = escape(email)
            rows += f"""
            <div class="row">
              <span>{safe_email}</span>
              <div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap">
                <form method="post" action="{prefix}/admin/users/reset-password"
                      style="display:flex;gap:.3rem;align-items:center">
                  <input type="hidden" name="email" value="{safe_email}">
                  <input type="password" name="new_password" placeholder="Nueva contraseña"
                         minlength="8" required
                         style="padding:.25rem .5rem;border:1px solid #ccc;border-radius:4px;font-size:.8rem;width:150px">
                  <button class="btn btn-primary btn-sm" type="submit">Resetear</button>
                </form>
                <form method="post" action="{prefix}/admin/users/delete" style="display:inline">
                  <input type="hidden" name="email" value="{safe_email}">
                  <button class="btn btn-danger btn-sm" type="submit"
                    onclick="return confirm('¿Eliminar {safe_email}?')">Eliminar</button>
                </form>
              </div>
            </div>"""
        users_html = rows
    else:
        users_html = '<div class="empty">Sin usuarios registrados.</div>'

    msg_html = f'<p style="color:#065f46;background:#d1fae5;padding:.5rem .75rem;border-radius:4px;margin-bottom:1rem;font-size:.9rem">{msg}</p>' if msg else ""

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin — Gastos</title>{_STYLE}</head><body>
<div class="card">
  <a class="back" href="{prefix}/">← Volver a la app</a>
  <h2>Panel de Administración</h2>
  {msg_html}

  <h3>Registro de usuarios</h3>
  <div class="row">
    <span>Estado: {badge}</span>
    {toggle_btn}
  </div>

  <h3>Usuarios registrados ({len(users)})</h3>
  {users_html}

  <h3>Copia de seguridad completa</h3>
  <p class="hint">Se lleva <b>TODO</b>: todos los usuarios y sus cuentas de login,
     sus datos y logs, las reglas y las credenciales de scrapers (cifradas).
     Ideal para reinstalar el add-on de cero y restaurar sin perder nada.</p>
  <div class="row">
    <span>Descargar copia (.zip)</span>
    <a class="btn btn-primary btn-sm" href="{prefix}/admin/export-all">Exportar todo</a>
  </div>
  <form method="post" action="{prefix}/admin/import-all" enctype="multipart/form-data"
        onsubmit="return confirm('Restaurar SOBRESCRIBE los datos actuales con los del backup. ¿Continuar?')">
    <div class="row">
      <input type="file" name="file" accept=".zip,application/zip" required>
      <button class="btn btn-danger btn-sm" type="submit">Restaurar todo</button>
    </div>
  </form>
  <p class="hint">⚠ Las credenciales de scrapers solo se descifran si la opción
     <code>scraper_encryption_key</code> del add-on sigue siendo la misma.
     Reiniciá el add-on después de restaurar para aplicar todo.</p>
</div>
</body></html>"""
    return HTMLResponse(html)


@router.get("", response_class=HTMLResponse)
async def admin_get(request: Request):
    if not _require_admin(request):
        return _redirect(request, "/")
    return _render_panel(request)


@router.post("/registration", response_class=HTMLResponse)
async def toggle_registration(request: Request, enabled: str = Form(...)):
    if not _require_admin(request):
        return _redirect(request, "/")
    val = enabled.lower() in ("true", "1", "yes")
    set_registration_enabled(val)
    estado = "activado" if val else "desactivado"
    return _render_panel(request, f"Registro de usuarios {estado}.")


@router.post("/users/delete", response_class=HTMLResponse)
async def admin_delete_user(request: Request, email: str = Form(...)):
    if not _require_admin(request):
        return _redirect(request, "/")
    delete_user(email.lower())
    return _render_panel(request, f"Usuario {escape(email)} eliminado.")


@router.post("/users/reset-password", response_class=HTMLResponse)
async def admin_reset_password(
    request: Request,
    email: str = Form(...),
    new_password: str = Form(...),
):
    if not _require_admin(request):
        return _redirect(request, "/")
    ok, err = reset_password(email.lower(), new_password)
    if not ok:
        return _render_panel(request, f"Error: {escape(err)}")
    return _render_panel(request, f"Contraseña de {escape(email)} actualizada.")


@router.get("/export-all")
async def admin_export_all(request: Request):
    """Descarga un .zip con TODO /data (todos los usuarios + credenciales cifradas)."""
    if not _require_admin(request):
        return _redirect(request, "/")
    if not os.path.isdir(DATA_DIR):
        raise HTTPException(404, "No hay datos para exportar todavía.")
    tmp_zip = _build_full_backup_zip(DATA_DIR)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        tmp_zip,
        media_type="application/zip",
        filename=f"snap-budget_full_{stamp}.zip",
        background=BackgroundTask(lambda: os.path.exists(tmp_zip) and os.unlink(tmp_zip)),
    )


@router.post("/import-all", response_class=HTMLResponse)
async def admin_import_all(request: Request, file: UploadFile = File(...)):
    """
    Restaura un backup completo (.zip de /admin/export-all). SOBRESCRIBE los
    archivos presentes en el backup; los usuarios/archivos que no estén en el
    backup quedan como están (merge, no wipe). Defensa anti zip-slip: cada
    miembro se valida con _safe_target y nunca escribe fuera de DATA_DIR.
    """
    if not _require_admin(request):
        return _redirect(request, "/")

    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return _render_panel(request, "Error: el archivo no es un .zip válido.")

    names = [n for n in zf.namelist() if not n.endswith("/")]
    if "users.json" not in names:
        return _render_panel(
            request,
            "Error: el backup no contiene users.json — no parece una copia completa "
            "de SnapBudget (¿usaste el export-backup per-usuario en vez de Exportar todo?).",
        )

    base_abs = os.path.abspath(DATA_DIR)
    os.makedirs(base_abs, exist_ok=True)
    restored = 0
    skipped: list[str] = []

    for name in names:
        if name == "backup_manifest.json":
            continue
        target = _safe_target(base_abs, name)
        if target is None:
            skipped.append(name)  # ruta peligrosa (zip-slip) — se descarta
            continue
        data = zf.read(name)
        # Validar que las .db sean SQLite reales antes de pisar nada.
        if name.endswith(".db") and not data.startswith(_SQLITE_MAGIC):
            skipped.append(name)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # Borrar WAL/SHM viejos para que SQLite no los aplique sobre la DB nueva.
        if name.endswith(".db"):
            for ext in ("-wal", "-shm"):
                p = target + ext
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        with open(target, "wb") as f:
            f.write(data)
        restored += 1

    msg = (f"Restaurados {restored} archivos. "
           "Reiniciá el add-on para aplicar todo (scheduler, sesiones, etc.).")
    if skipped:
        msg += f" Se ignoraron {len(skipped)} entradas inseguras o inválidas."
    return _render_panel(request, msg)

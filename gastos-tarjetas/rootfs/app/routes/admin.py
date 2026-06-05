import re
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import (
    get_registration_enabled, set_registration_enabled,
    list_users, delete_user, reset_password,
)

router = APIRouter()

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

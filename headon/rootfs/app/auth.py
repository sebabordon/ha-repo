import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

ALLOWED_DOMAIN = os.environ.get("ALLOWED_DOMAIN", "example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
_reg_env = os.environ.get("REGISTRATION_ENABLED", "false").lower()
REGISTRATION_ENABLED_DEFAULT = _reg_env in ("1", "true", "yes")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
SESSION_TOKENS_FILE = os.path.join(DATA_DIR, "session_tokens.json")
ADMIN_EMAIL = f"admin@{ALLOWED_DOMAIN}"
_MAX_TOKENS_PER_USER = 50

_login_failures: dict[str, list[float]] = defaultdict(list)
_MAX_FAILURES = 10
_WINDOW_SECS = 900

_SAFE_PREFIX_RE = re.compile(r'^(/[a-zA-Z0-9_/-]*)?$')


def _atomic_write_json(path: str, obj) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


# ── Settings ─────────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_settings(s: dict):
    _atomic_write_json(SETTINGS_FILE, s)

def get_registration_enabled() -> bool:
    s = _load_settings()
    if "registration_enabled" in s:
        return bool(s["registration_enabled"])
    return REGISTRATION_ENABLED_DEFAULT

def set_registration_enabled(val: bool):
    s = _load_settings()
    s["registration_enabled"] = val
    _save_settings(s)


# ── Session tokens ───────────────────────────────────────────────────────────

def _load_session_tokens() -> dict:
    try:
        with open(SESSION_TOKENS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_session_tokens(d: dict):
    _atomic_write_json(SESSION_TOKENS_FILE, d)

def issue_session_token(email: str) -> str:
    email = email.lower()
    d = _load_session_tokens()
    tokens = d.get(email, [])
    token = secrets.token_urlsafe(32)
    tokens.append(token)
    if len(tokens) > _MAX_TOKENS_PER_USER:
        tokens = tokens[-_MAX_TOKENS_PER_USER:]
    d[email] = tokens
    _save_session_tokens(d)
    return token

def revoke_session_token(email: str, token: str) -> None:
    if not email or not token:
        return
    email = email.lower()
    d = _load_session_tokens()
    tokens = d.get(email, [])
    if token in tokens:
        tokens.remove(token)
        d[email] = tokens
        _save_session_tokens(d)

def revoke_all_session_tokens(email: str) -> None:
    if not email:
        return
    d = _load_session_tokens()
    d.pop(email.lower(), None)
    _save_session_tokens(d)

def is_session_token_valid(email: str, token: str) -> bool:
    if not email or not token:
        return False
    d = _load_session_tokens()
    return token in d.get(email.lower(), [])


# ── Users ────────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def _save_users(users: dict):
    _atomic_write_json(USERS_FILE, users)

def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()

def verify_password(email: str, password: str) -> bool:
    users = _load_users()
    entry = users.get(email)
    if not entry:
        return False
    return hmac.compare_digest(_hash(password, entry["salt"]), entry["hash"])

def verify_admin(email: str, password: str) -> bool:
    if not ADMIN_PASSWORD:
        return False
    return email.lower() == ADMIN_EMAIL and hmac.compare_digest(password, ADMIN_PASSWORD)

def create_user(email: str, password: str, skip_checks: bool = False) -> tuple[bool, str]:
    if not skip_checks:
        if not get_registration_enabled():
            return False, "El registro de nuevos usuarios está deshabilitado."
        if not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
            return False, f"Solo se permiten emails @{ALLOWED_DOMAIN}"
    if email.lower() == ADMIN_EMAIL:
        return False, "Ese email no está disponible."
    users = _load_users()
    if email in users:
        return False, "El usuario ya existe"
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    salt = os.urandom(16).hex()
    users[email] = {"hash": _hash(password, salt), "salt": salt}
    _save_users(users)
    return True, ""

def list_users() -> list[str]:
    return sorted(_load_users().keys())

def delete_user(email: str) -> bool:
    users = _load_users()
    if email not in users:
        return False
    del users[email]
    _save_users(users)
    revoke_all_session_tokens(email)
    return True

def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    users = _load_users()
    if email not in users:
        return False, "Usuario no encontrado."
    salt = os.urandom(16).hex()
    users[email] = {"hash": _hash(new_password, salt), "salt": salt}
    _save_users(users)
    revoke_all_session_tokens(email)
    return True, ""

def require_auth(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not is_session_token_valid(user.get("email", ""), user.get("stoken", "")):
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sesión expirada")
    return user


# ── Auth routes ──────────────────────────────────────────────────────────────

router = APIRouter()

_STYLE = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#fff;padding:2rem;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.1);width:340px}
h2{margin-bottom:1.5rem;text-align:center;font-size:1.2rem;color:#16213e}
.field{margin-bottom:1rem}
input{width:100%;padding:.6rem .8rem;border:1px solid #ccc;border-radius:4px;font-size:.95rem}
input:focus{outline:none;border-color:#16213e}
.btn{width:100%;padding:.75rem;background:#16213e;color:#fff;border:none;
     border-radius:4px;font-size:1rem;cursor:pointer;margin-top:.25rem}
.btn:hover{background:#0f3460}
.err{color:#c00;font-size:.88rem;margin-bottom:1rem;padding:.5rem;background:#fff0f0;border-radius:4px}
.link{text-align:center;margin-top:1rem;font-size:.88rem;color:#666}
.link a{color:#16213e;text-decoration:none;font-weight:500}
</style>"""

_LOGIN_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HeadOn</title>{style}</head><body>
<div class="card">
  <h2>🧠 HeadOn</h2>
  {error}
  <form method="post" action="{prefix}/auth/login">
    <div class="field"><input type="email" name="email" placeholder="Email (@{domain})" required autofocus></div>
    <div class="field"><input type="password" name="password" placeholder="Contraseña" required></div>
    <button class="btn" type="submit">Ingresar</button>
  </form>
  {register_link}
</div></body></html>"""

_REGISTER_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HeadOn — Registro</title>{style}</head><body>
<div class="card">
  <h2>Crear cuenta</h2>
  {error}
  <form method="post" action="{prefix}/auth/register">
    <div class="field"><input type="email" name="email" placeholder="Email (@{domain})" required autofocus></div>
    <div class="field"><input type="password" name="password" placeholder="Contraseña" required minlength="8"></div>
    <div class="field"><input type="password" name="password2" placeholder="Repetir contraseña" required></div>
    <button class="btn" type="submit">Registrarme</button>
  </form>
  <div class="link"><a href="{prefix}/auth/login">Ya tengo cuenta</a></div>
</div></body></html>"""


def _safe_prefix(request: Request) -> str:
    prefix = request.headers.get("X-Ingress-Path", "")
    return prefix if _SAFE_PREFIX_RE.match(prefix) else ""

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    _login_failures[ip] = [t for t in _login_failures[ip] if now - t < _WINDOW_SECS]
    return len(_login_failures[ip]) >= _MAX_FAILURES

def _record_failure(ip: str) -> None:
    _login_failures[ip].append(time.monotonic())

def _render(template: str, error: str = "", ingress_prefix: str = "", **kwargs) -> HTMLResponse:
    err_html = f'<div class="err">{error}</div>' if error else ""
    register_link = (
        f'<div class="link"><a href="{ingress_prefix}/auth/register">Crear cuenta</a></div>'
        if get_registration_enabled() else ""
    )
    return HTMLResponse(template.format(
        style=_STYLE, error=err_html, domain=ALLOWED_DOMAIN,
        prefix=ingress_prefix, register_link=register_link, **kwargs
    ))

def _redirect(request: Request, path: str, status_code: int = 307) -> RedirectResponse:
    prefix = _safe_prefix(request)
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("user"):
        return _redirect(request, "/")
    return _render(_LOGIN_HTML, ingress_prefix=_safe_prefix(request))

@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    prefix = _safe_prefix(request)
    ip = _client_ip(request)
    if _is_rate_limited(ip):
        return _render(_LOGIN_HTML, "Demasiados intentos fallidos. Intentá de nuevo en 15 minutos.",
                       ingress_prefix=prefix)
    email = email.lower()
    is_admin = verify_admin(email, password)
    if is_admin or verify_password(email, password):
        request.session["user"] = {
            "email": email, "is_admin": is_admin,
            "stoken": issue_session_token(email),
        }
        return _redirect(request, "/", status_code=303)
    _record_failure(ip)
    return _render(_LOGIN_HTML, "Email o contraseña incorrectos.", ingress_prefix=prefix)

@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    prefix = _safe_prefix(request)
    if not get_registration_enabled():
        return _render(_LOGIN_HTML, "El registro de nuevos usuarios está deshabilitado.", ingress_prefix=prefix)
    return _render(_REGISTER_HTML, ingress_prefix=prefix)

@router.post("/register", response_class=HTMLResponse)
async def register_post(request: Request, email: str = Form(...),
                        password: str = Form(...), password2: str = Form(...)):
    prefix = _safe_prefix(request)
    if not get_registration_enabled():
        return _render(_LOGIN_HTML, "El registro de nuevos usuarios está deshabilitado.", ingress_prefix=prefix)
    if password != password2:
        return _render(_REGISTER_HTML, "Las contraseñas no coinciden.", ingress_prefix=prefix)
    if len(password) < 8:
        return _render(_REGISTER_HTML, "La contraseña debe tener al menos 8 caracteres.", ingress_prefix=prefix)
    ok, err = create_user(email.lower(), password)
    if not ok:
        return _render(_REGISTER_HTML, err, ingress_prefix=prefix)
    request.session["user"] = {
        "email": email.lower(), "is_admin": False,
        "stoken": issue_session_token(email.lower()),
    }
    return _redirect(request, "/", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    user = request.session.get("user")
    if user and user.get("email"):
        revoke_session_token(user["email"], user.get("stoken", ""))
    request.session.clear()
    resp = _redirect(request, "/auth/login")
    resp.delete_cookie("session", path="/")
    return resp

@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return {}
    return {"email": user.get("email", ""), "is_admin": user.get("is_admin", False)}


# ── Admin routes ─────────────────────────────────────────────────────────────

admin_router = APIRouter()

_ADMIN_STYLE = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#f0f2f5;min-height:100vh;padding:2rem 1rem}
.card{background:#fff;padding:2rem;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.1);
      max-width:600px;margin:0 auto}
h2{margin-bottom:1.5rem;font-size:1.2rem;color:#16213e}
h3{margin:1.5rem 0 .75rem;font-size:1rem;color:#16213e;border-bottom:1px solid #eee;padding-bottom:.4rem}
.row{display:flex;align-items:center;justify-content:space-between;padding:.5rem 0;
     border-bottom:1px solid #f0f0f0}
.badge{display:inline-block;padding:.2rem .6rem;border-radius:12px;font-size:.8rem;font-weight:600}
.badge-on{background:#d1fae5;color:#065f46}
.badge-off{background:#fee2e2;color:#991b1b}
.btn{padding:.5rem 1rem;border:none;border-radius:4px;font-size:.9rem;cursor:pointer;font-weight:500}
.btn-primary{background:#16213e;color:#fff}
.btn-danger{background:#ef4444;color:#fff}
.btn-sm{padding:.3rem .7rem;font-size:.8rem}
.back{display:inline-block;margin-bottom:1.5rem;color:#16213e;text-decoration:none;font-size:.9rem}
.empty{color:#aaa;font-size:.9rem;padding:.5rem 0}
a.btn{text-decoration:none;display:inline-block}
</style>"""

def _require_admin(request: Request):
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        return None
    return user

def _admin_redirect(request: Request, path: str, status_code: int = 303) -> RedirectResponse:
    prefix = _safe_prefix(request)
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)

def _render_admin(request: Request, msg: str = "") -> HTMLResponse:
    from html import escape
    prefix = _safe_prefix(request)
    reg = get_registration_enabled()
    users = list_users()
    badge = '<span class="badge badge-on">ACTIVADO</span>' if reg else '<span class="badge badge-off">DESACTIVADO</span>'
    toggle_label = "Desactivar" if reg else "Activar"
    toggle_btn = f'<form method="post" action="{prefix}/admin/registration" style="display:inline"><input type="hidden" name="enabled" value="{"false" if reg else "true"}"><button class="btn btn-primary btn-sm" type="submit">{toggle_label}</button></form>'

    users_html = ""
    if users:
        for email in users:
            safe = escape(email)
            users_html += f'''<div class="row"><span>{safe}</span>
            <div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap">
            <form method="post" action="{prefix}/admin/users/reset-password" style="display:flex;gap:.3rem;align-items:center">
              <input type="hidden" name="email" value="{safe}">
              <input type="password" name="new_password" placeholder="Nueva contraseña" minlength="8" required style="padding:.25rem .5rem;border:1px solid #ccc;border-radius:4px;font-size:.8rem;width:150px">
              <button class="btn btn-primary btn-sm" type="submit">Resetear</button>
            </form>
            <form method="post" action="{prefix}/admin/users/delete" style="display:inline">
              <input type="hidden" name="email" value="{safe}">
              <button class="btn btn-danger btn-sm" type="submit" onclick="return confirm('¿Eliminar {safe}?')">Eliminar</button>
            </form></div></div>'''
    else:
        users_html = '<div class="empty">Sin usuarios registrados.</div>'

    msg_html = f'<p style="color:#065f46;background:#d1fae5;padding:.5rem .75rem;border-radius:4px;margin-bottom:1rem;font-size:.9rem">{msg}</p>' if msg else ""

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin — HeadOn</title>{_ADMIN_STYLE}</head><body>
<div class="card">
  <a class="back" href="{prefix}/">← Volver a la app</a>
  <h2>Panel de Administración</h2>
  {msg_html}
  <h3>Registro de usuarios</h3>
  <div class="row"><span>Estado: {badge}</span>{toggle_btn}</div>
  <h3>Crear usuario</h3>
  <form method="post" action="{prefix}/admin/users/create" style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;padding:.5rem 0">
    <input type="email" name="email" placeholder="Email (cualquier dominio)" required style="padding:.25rem .5rem;border:1px solid #ccc;border-radius:4px;font-size:.85rem;flex:1;min-width:180px">
    <input type="password" name="password" placeholder="Contraseña" minlength="8" required style="padding:.25rem .5rem;border:1px solid #ccc;border-radius:4px;font-size:.85rem;width:140px">
    <button class="btn btn-primary btn-sm" type="submit">Crear</button>
  </form>

  <h3>Usuarios registrados ({len(users)})</h3>
  {users_html}
</div></body></html>"""
    return HTMLResponse(html)


@admin_router.get("", response_class=HTMLResponse)
async def admin_get(request: Request):
    if not _require_admin(request):
        return _admin_redirect(request, "/")
    return _render_admin(request)

@admin_router.post("/registration", response_class=HTMLResponse)
async def toggle_registration(request: Request, enabled: str = Form(...)):
    if not _require_admin(request):
        return _admin_redirect(request, "/")
    val = enabled.lower() in ("true", "1", "yes")
    set_registration_enabled(val)
    return _render_admin(request, f"Registro de usuarios {'activado' if val else 'desactivado'}.")

@admin_router.post("/users/create", response_class=HTMLResponse)
async def admin_create_user(request: Request, email: str = Form(...), password: str = Form(...)):
    from html import escape
    if not _require_admin(request):
        return _admin_redirect(request, "/")
    ok, err = create_user(email.lower(), password, skip_checks=True)
    if not ok:
        return _render_admin(request, f"Error: {escape(err)}")
    return _render_admin(request, f"Usuario {escape(email)} creado.")

@admin_router.post("/users/delete", response_class=HTMLResponse)
async def admin_delete_user(request: Request, email: str = Form(...)):
    from html import escape
    if not _require_admin(request):
        return _admin_redirect(request, "/")
    delete_user(email.lower())
    return _render_admin(request, f"Usuario {escape(email)} eliminado.")

@admin_router.post("/users/reset-password", response_class=HTMLResponse)
async def admin_reset_password(request: Request, email: str = Form(...), new_password: str = Form(...)):
    from html import escape
    if not _require_admin(request):
        return _admin_redirect(request, "/")
    ok, err = reset_password(email.lower(), new_password)
    if not ok:
        return _render_admin(request, f"Error: {escape(err)}")
    return _render_admin(request, f"Contraseña de {escape(email)} actualizada.")

import re
import time
from collections import defaultdict

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import (
    create_user, verify_password, verify_admin, get_registration_enabled,
    ADMIN_EMAIL, issue_session_token, revoke_session_token,
)
from config import ALLOWED_DOMAIN

# ── Rate limiting (in-memory, por IP) ─────────────────────────────────────────
_login_failures: dict[str, list[float]] = defaultdict(list)
_MAX_FAILURES  = 10
_WINDOW_SECS   = 900  # 15 minutos

_SAFE_PREFIX_RE = re.compile(r'^(/[a-zA-Z0-9_/-]*)?$')


def _safe_prefix(request: Request) -> str:
    prefix = request.headers.get("X-Ingress-Path", "")
    return prefix if _SAFE_PREFIX_RE.match(prefix) else ""


def _client_ip(request: Request) -> str:
    """IP usada como bucket del rate limiter.

    Usa SIEMPRE el peer TCP real (`request.client.host`), no los headers
    `X-Forwarded-For` / `X-Real-IP`: esos los controla el cliente y, en el
    acceso directo al puerto 8000 (sin la auth de HA), un atacante los cambiaría
    en cada intento para evadir el límite de fuerza bruta. El peer TCP no se
    puede falsificar.

    Trade-off: por ingress todos los logins comparten la IP del proxy de HA y
    por ende un mismo bucket. Es aceptable porque ese camino ya exige estar
    autenticado en Home Assistant; el vector real es el acceso directo.
    """
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    _login_failures[ip] = [t for t in _login_failures[ip] if now - t < _WINDOW_SECS]
    return len(_login_failures[ip]) >= _MAX_FAILURES


def _record_failure(ip: str) -> None:
    _login_failures[ip].append(time.monotonic())

router = APIRouter()

_STYLE = """
<style>
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
</style>
"""

_LOGIN_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Me</title>{style}</head><body>
<div class="card">
  <h2>Finance Me</h2>
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
<title>Finance Me — Registro</title>{style}</head><body>
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
    prefix = _safe_prefix(request)
    return _render(_LOGIN_HTML, ingress_prefix=prefix)


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
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
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
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
    # Revocar el token de ESTA sesión server-side: aunque el navegador no borre
    # la cookie (iOS PWA standalone, cookie duplicada por path del proxy, etc.),
    # la cookie vieja deja de autenticar en el próximo request.
    user = request.session.get("user")
    if user and user.get("email"):
        revoke_session_token(user["email"], user.get("stoken", ""))
    request.session.clear()
    resp = _redirect(request, "/auth/login")
    # Borrado explícito además del que hace SessionMiddleware al ver la sesión
    # vacía — belt-and-suspenders con el mismo path con que se setea la cookie.
    resp.delete_cookie("session", path="/")
    return resp


@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return {}
    return {"email": user.get("email", ""), "is_admin": user.get("is_admin", False)}

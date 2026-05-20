from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import create_user, verify_password
from config import ALLOWED_DOMAIN

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
<title>Gastos Tarjetas</title>{style}</head><body>
<div class="card">
  <h2>Gastos Tarjetas</h2>
  {error}
  <form method="post" action="{prefix}/auth/login">
    <div class="field"><input type="email" name="email" placeholder="Email (@{domain})" required autofocus></div>
    <div class="field"><input type="password" name="password" placeholder="Contraseña" required></div>
    <button class="btn" type="submit">Ingresar</button>
  </form>
  <div class="link"><a href="{prefix}/auth/register">Crear cuenta</a></div>
</div></body></html>"""

_REGISTER_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gastos Tarjetas — Registro</title>{style}</head><body>
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


def _render(template: str, error: str = "", ingress_prefix: str = "") -> HTMLResponse:
    err_html = f'<div class="err">{error}</div>' if error else ""
    return HTMLResponse(template.format(style=_STYLE, error=err_html, domain=ALLOWED_DOMAIN, prefix=ingress_prefix))


def _redirect(request: Request, path: str, status_code: int = 307) -> RedirectResponse:
    prefix = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("user"):
        return _redirect(request, "/")
    prefix = request.headers.get("X-Ingress-Path", "")
    return _render(_LOGIN_HTML, ingress_prefix=prefix)


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if verify_password(email.lower(), password):
        request.session["user"] = {"email": email.lower()}
        return _redirect(request, "/", status_code=303)
    prefix = request.headers.get("X-Ingress-Path", "")
    return _render(_LOGIN_HTML, "Email o contraseña incorrectos.", ingress_prefix=prefix)


@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    prefix = request.headers.get("X-Ingress-Path", "")
    return _render(_REGISTER_HTML, ingress_prefix=prefix)


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    prefix = request.headers.get("X-Ingress-Path", "")
    if password != password2:
        return _render(_REGISTER_HTML, "Las contraseñas no coinciden.", ingress_prefix=prefix)
    if len(password) < 8:
        return _render(_REGISTER_HTML, "La contraseña debe tener al menos 8 caracteres.", ingress_prefix=prefix)
    ok, err = create_user(email.lower(), password)
    if not ok:
        return _render(_REGISTER_HTML, err, ingress_prefix=prefix)
    request.session["user"] = {"email": email.lower()}
    return _redirect(request, "/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return _redirect(request, "/auth/login")


@router.get("/me")
async def me(request: Request):
    return request.session.get("user") or {}

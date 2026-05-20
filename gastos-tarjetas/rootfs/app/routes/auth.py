from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from auth import oauth, require_auth
from config import ALLOWED_DOMAIN

router = APIRouter()


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    if not user:
        return RedirectResponse("/auth/login")

    email: str = user.get("email", "")
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return HTMLResponse(f"<h2>Acceso restringido a @{ALLOWED_DOMAIN}</h2>", status_code=403)

    request.session["user"] = {"email": email, "name": user.get("name", "")}
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login")


@router.get("/me")
async def me(request: Request):
    return request.session.get("user") or {}

"""Login SSO vía OIDC (pensado para authentik) — Authorization Code flow.

Convive con el login local: cuando SSO_ENABLED es true se agrega el botón
"Iniciar sesión con SSO" en /auth/login, pero el form de email/password y
ADMIN_PASSWORD siguen funcionando igual que antes (fallback si authentik
está caído). El primer login SSO de un email @ALLOWED_DOMAIN auto-provisiona
el usuario local (ver ensure_sso_user en auth.py); el rol admin se decide con
el mismo criterio que el login local: email == ADMIN_EMAIL.
"""
import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from auth import ADMIN_EMAIL, ensure_sso_user, issue_session_token
from config import ALLOWED_DOMAIN
from sso_config import SSO_ENABLED, OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_ADMIN_GROUP

router = APIRouter()

_SAFE_PREFIX_RE = re.compile(r'^(/[a-zA-Z0-9_/-]*)?$')

_oauth = None
if SSO_ENABLED:
    from authlib.integrations.starlette_client import OAuth
    _oauth = OAuth()
    _oauth.register(
        name="authentik",
        server_metadata_url=f"{OIDC_ISSUER}/.well-known/openid-configuration",
        client_id=OIDC_CLIENT_ID,
        client_secret=OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )


def _safe_prefix(request: Request) -> str:
    prefix = request.headers.get("X-Ingress-Path", "")
    return prefix if _SAFE_PREFIX_RE.match(prefix) else ""


def _external_base(request: Request) -> str:
    # Detrás de un reverse proxy (Nginx Proxy Manager): confiar en los headers
    # X-Forwarded-* para armar una redirect_uri https, no la que ve uvicorn
    # directamente (que sin esos headers sería http).
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host}"


@router.get("/login")
async def sso_login(request: Request):
    prefix = _safe_prefix(request)
    if not SSO_ENABLED:
        return RedirectResponse(f"{prefix}/auth/login")
    redirect_uri = f"{_external_base(request)}{prefix}/auth/sso/callback"
    return await _oauth.authentik.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def sso_callback(request: Request):
    prefix = _safe_prefix(request)
    if not SSO_ENABLED:
        return RedirectResponse(f"{prefix}/auth/login")

    from authlib.integrations.starlette_client import OAuthError
    try:
        token = await _oauth.authentik.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{prefix}/auth/login?error=sso")

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").strip().lower()
    if not email or not (email == ADMIN_EMAIL or email.endswith(f"@{ALLOWED_DOMAIN}")):
        return RedirectResponse(f"{prefix}/auth/login?error=sso_domain")

    ensure_sso_user(email)
    groups = userinfo.get("groups") or []
    is_admin = email == ADMIN_EMAIL or (OIDC_ADMIN_GROUP and OIDC_ADMIN_GROUP in groups)
    request.session["user"] = {
        "email": email, "is_admin": is_admin,
        "stoken": issue_session_token(email),
    }
    return RedirectResponse(f"{prefix}/", status_code=303)

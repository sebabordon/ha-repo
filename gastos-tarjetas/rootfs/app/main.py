import os
import re
import secrets
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from routes import upload, gastos, rules, stats, auth, cuentas, presupuesto, admin, config_route, charts, cuotas
from routes import scrapers as scrapers_routes
from routes import scraper_instances_routes
from routes import categorias_route
from routes import logs as logs_route
from routes import push as push_route
from routes import pagos as pagos_route
from db import init_db
from config import APP_VERSION
from scraper_scheduler import start_scheduler
import userctx

def _load_session_secret() -> str:
    """Lee (o genera) el secreto de sesión desde /data/session_secret.

    Leer desde archivo en lugar de env var garantiza que el secreto sea el
    mismo en todos los reinicios del proceso, independientemente de cómo el
    supervisor arranque uvicorn.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    data_dir    = os.environ.get("DATA_DIR", "/data")
    secret_file = os.path.join(data_dir, "session_secret")
    try:
        with open(secret_file) as f:
            secret = f.read().strip()
        if secret:
            return secret
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log.warning("No se pudo leer session_secret: %s — generando uno temporal", exc)

    # Generar y persistir un secreto nuevo
    secret = secrets.token_urlsafe(48)
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(secret_file, "w") as f:
            f.write(secret)
        os.chmod(secret_file, 0o600)
        _log.info("SESSION_SECRET generado y guardado en %s", secret_file)
    except Exception as exc:
        _log.warning("No se pudo persistir session_secret: %s — las sesiones no sobrevivan reinicios", exc)
    return secret


app = FastAPI(title="SnapBudget", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def on_startup():
    init_db()          # inicializa la DB raíz (fuente de migraciones)
    # Instalar handler de log unificado (escribe en app_log table)
    from app_log import setup_db_log_handler
    setup_db_log_handler()
    start_scheduler()  # arranca scrapers programados (no-op si no hay scrapers.yaml)


# ── Per-user data context middleware ─────────────────────────────────────────
# Tracks which users have already had init_db() run this process lifetime so
# we don't repeat the (cheap but non-zero) work on every request.
_initialized_users: set[str] = set()


@app.middleware("http")
async def user_data_context(request: Request, call_next):
    """Set the per-user data directory for the duration of each request."""
    user = request.session.get("user")
    # Validar el token de sesión server-side. Una cookie revocada (logout en
    # otro request, reset de password) o anterior al esquema de tokens se
    # descarta acá: se limpia la sesión (SessionMiddleware borrará la cookie) y
    # se trata el request como no autenticado. Esto evita que una cookie vieja
    # re-loguee al usuario anterior tras un logout/login.
    if user and user.get("email"):
        from auth import is_session_token_valid
        if not is_session_token_valid(user["email"], user.get("stoken", "")):
            request.session.clear()
            user = None
    token = None
    if user and user.get("email"):
        email = user["email"]
        token = userctx.set_user_context(email)
        if email not in _initialized_users:
            init_db()  # create/migrate tables in this user's DB
            # Proceso nuevo → limpiar scrapers que quedaron 'running' (scrape muerto
            # por un update/reinicio del add-on), para que el chip no quede pegado.
            try:
                from scrapers_db import reset_stale_running
                reset_stale_running()
            except Exception:
                pass
            _initialized_users.add(email)
    try:
        response = await call_next(request)
    finally:
        if token is not None:
            userctx.reset_user_context(token)
    return response

app.add_middleware(
    SessionMiddleware,
    secret_key=_load_session_secret(),
    same_site="lax",
    https_only=False,  # ingress termina TLS; el acceso directo por LAN puede ser HTTP
    max_age=14 * 24 * 3600,
)
# Nota: NO se habilita CORS. La app es una PWA same-origin (ingress / puerto
# propio); no hay consumidor cross-origin legítimo. Un `allow_origins=["*"]` con
# `allow_credentials=True` permitiría a cualquier sitio web hacer requests con la
# cookie de sesión del usuario y leer sus datos. Si en el futuro hace falta un
# cliente externo, agregar CORS acotado a orígenes explícitos (nunca "*").

app.include_router(auth.router,       prefix="/auth", tags=["auth"])
app.include_router(upload.router,     prefix="/api",  tags=["upload"])
app.include_router(gastos.router,     prefix="/api",  tags=["gastos"])
app.include_router(rules.router,      prefix="/api",  tags=["rules"])
app.include_router(stats.router,      prefix="/api",  tags=["stats"])
app.include_router(cuentas.router,    prefix="/api",  tags=["cuentas"])
app.include_router(presupuesto.router,  prefix="/api",   tags=["presupuesto"])
app.include_router(config_route.router, prefix="/api",   tags=["config"])
app.include_router(charts.router,          prefix="/api",   tags=["charts"])
app.include_router(cuotas.router,          prefix="/api",   tags=["cuotas"])
app.include_router(scrapers_routes.router, prefix="/api",   tags=["scrapers"])
app.include_router(scraper_instances_routes.router, prefix="/api", tags=["scraper_instances"])
app.include_router(categorias_route.router, prefix="/api",   tags=["categorias"])
app.include_router(logs_route.router,       prefix="/api",   tags=["logs"])
app.include_router(push_route.router,        prefix="/api",   tags=["push"])
app.include_router(pagos_route.router,       prefix="/api",   tags=["pagos"])
app.include_router(admin.router,            prefix="/admin", tags=["admin"])

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/manifest.json")
async def serve_manifest(request: Request):
    """PWA manifest dinámico — incluye shortcuts del usuario si está logueado."""
    shortcuts = []
    user = request.session.get("user")
    if user and user.get("email"):
        try:
            from user_config import read_user_config
            cfg = read_user_config()
            for sc in cfg.get("pwa_shortcuts", []):
                fuente = sc.get("fuente", "")
                label  = sc.get("label", fuente)
                if fuente:
                    shortcuts.append({
                        "name":        label,
                        "url":         f"/quick?fuente={fuente}&label={label}",
                        "description": f"Cargar gasto {label}",
                    })
        except Exception:
            pass

    manifest = {
        "name":             "SnapBudget",
        "short_name":       "SnapBudget",
        "description":      "SnapBudget — gestor de gastos de tarjetas",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#16213e",
        "theme_color":      "#16213e",
        "icons": [
            {
                "src":     "/static/icono-sb.png",
                "sizes":   "1024x1024",
                "type":    "image/png",
                "purpose": "any maskable",
            },
            {
                "src":   "/static/icono-sb.svg",
                "sizes": "any",
                "type":  "image/svg+xml",
            },
        ],
    }
    if shortcuts:
        manifest["shortcuts"] = shortcuts

    return JSONResponse(manifest, media_type="application/manifest+json")


@app.get("/quick")
async def serve_quick(request: Request, fuente: str = "", label: str = ""):
    """
    Formulario rápido de carga de gastos.
    Inyecta título dinámico para que "Agregar al inicio" en Safari
    sugiera el nombre correcto (ej. "AMEX", "BBVA Cuenta").
    """
    user = request.session.get("user")
    if not user:
        return _redirect(request, "/auth/login")
    from html import escape as _esc
    from urllib.parse import quote as _q
    title = label.strip() or fuente.upper().replace("_", " ") or "Gasto rápido"
    # `label`/`fuente` vienen de la query string → escapar SIEMPRE antes de
    # interpolarlos en HTML (evita XSS reflejado). `quote=True` también escapa
    # las comillas para que no rompan el atributo content="...".
    title_html = _esc(title, quote=True)
    with open("static/quick.html") as f:
        html = f.read()
    html = html.replace("<title>Gasto Rápido</title>", f"<title>{title_html}</title>")
    html = html.replace(
        'content="SnapBudget"',
        f'content="{title_html}"',
        1,  # solo el primer apple-mobile-web-app-title
    )
    # Apunta al manifest específico del formulario rápido (con el nombre correcto).
    # URL-encodear los params: evita romper el atributo y la query.
    html = html.replace(
        'href="/manifest.json"',
        f'href="/manifest-quick.json?fuente={_q(fuente)}&label={_q(label)}"',
    )
    return HTMLResponse(html)


@app.get("/manifest-quick.json")
async def serve_manifest_quick(fuente: str = "", label: str = ""):
    """Manifest mínimo para las páginas /quick — con el nombre e ícono de la cuenta."""
    title = label.strip() or fuente.upper().replace("_", " ") or "Gasto rápido"
    style  = _icon_style(fuente)
    manifest = {
        "name":             title,
        "short_name":       title,
        "description":      f"Cargar gasto {title}",
        "start_url":        f"/quick?fuente={fuente}&label={label}",
        "display":          "standalone",
        "background_color": style["bg"],
        "theme_color":      style["bg"],
        "icons": [
            {
                "src":     f"/quick-icon/{fuente}.svg",
                "sizes":   "any",
                "type":    "image/svg+xml",
                "purpose": "any maskable",
            },
        ],
    }
    return JSONResponse(manifest, media_type="application/manifest+json")


# ── Paleta de íconos por fuente ────────────────────────────────────────────────
# Fallback por defecto. La paleta efectiva se obtiene con _icon_style(), que
# mergea las overrides del usuario (Config → Interfaz → Íconos PWA) por encima.
_FUENTE_ICON_STYLES: dict[str, dict] = {
    "amex":        {"bg": "#016FD0", "lines": ["AMEX"],          "fg": "#FFFFFF"},
    "mercadopago": {"bg": "#009EE3", "lines": ["MP"],            "fg": "#FFFFFF"},
    "bbva_mc":     {"bg": "#004481", "lines": ["BBVA", "MC"],    "fg": "#FFFFFF"},
    "bbva_visa":   {"bg": "#004481", "lines": ["BBVA", "VISA"],  "fg": "#FFFFFF"},
    "bbva_cuenta": {"bg": "#004481", "lines": ["BBVA", "CTA"],   "fg": "#FFFFFF"},
    "galicia_mc":  {"bg": "#E31837", "lines": ["GAL", "MC"],     "fg": "#FFFFFF"},
    "__default__": {"bg": "#16213e", "lines": [],                "fg": "#FFFFFF"},
}


def _icon_style(fuente: str) -> dict:
    """Estilo de ícono para `fuente`: override del usuario > default hardcodeado."""
    style = dict(_FUENTE_ICON_STYLES.get(fuente, _FUENTE_ICON_STYLES["__default__"]))
    try:
        from user_config import read_user_config
        overrides = (read_user_config().get("fuente_icon_styles") or {}).get(fuente)
        if isinstance(overrides, dict):
            for k in ("bg", "fg", "lines"):
                if overrides.get(k):
                    style[k] = overrides[k]
    except Exception:
        pass
    return style


@app.get("/quick-icon/{fuente}.svg")
async def quick_icon_svg(fuente: str):
    """Genera un ícono SVG con el color y sigla del banco."""
    from html import escape as _esc
    style = _icon_style(fuente)
    bg, fg = style["bg"], style["fg"]
    lines  = style["lines"] or [fuente[:4].upper()]
    # `fuente` (path param) y `lines` (overrides de config de usuario) se
    # interpolan en el SVG → escapar para que no inyecten markup/script.
    lines = [_esc(str(l), quote=True) for l in lines]
    bg, fg = _esc(str(bg), quote=True), _esc(str(fg), quote=True)

    # Dos líneas → fuente más chica y posicionadas arriba/abajo del centro
    if len(lines) == 1:
        text_els = f'<text x="256" y="310" text-anchor="middle" font-family="system-ui,sans-serif" font-size="180" font-weight="800" fill="{fg}" letter-spacing="-4">{lines[0]}</text>'
    else:
        text_els = (
            f'<text x="256" y="240" text-anchor="middle" font-family="system-ui,sans-serif" font-size="150" font-weight="800" fill="{fg}" letter-spacing="-3">{lines[0]}</text>'
            f'<text x="256" y="390" text-anchor="middle" font-family="system-ui,sans-serif" font-size="130" font-weight="700" fill="{fg}" opacity="0.85" letter-spacing="-2">{lines[1]}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="90" fill="{bg}"/>
  {text_els}
</svg>"""
    return PlainTextResponse(svg, media_type="image/svg+xml",
                             headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sw.js")
async def serve_sw():
    """Service worker — served from root with versioned cache name to bust stale caches."""
    with open("static/sw.js") as f:
        content = f.read()
    # Inject the current app version so cache name changes on every release,
    # invalidating cached static assets automatically.
    content = content.replace('"gastos-v0.2.32"', f'"gastos-v{APP_VERSION}"')
    return PlainTextResponse(
        content,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


_SAFE_PREFIX_RE = re.compile(r'^(/[a-zA-Z0-9_/-]*)?$')


def _safe_prefix(request: Request) -> str:
    prefix = request.headers.get("X-Ingress-Path", "")
    return prefix if _SAFE_PREFIX_RE.match(prefix) else ""


def _redirect(request: Request, path: str, status_code: int = 307) -> RedirectResponse:
    prefix = _safe_prefix(request)
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return _redirect(request, "/auth/login")
    prefix = _safe_prefix(request)
    with open("static/index.html") as f:
        html = f.read()
    html = html.replace('href="/static/', f'href="{prefix}/static/')
    html = html.replace('src="/static/', f'src="{prefix}/static/')
    html = html.replace('href="/auth/', f'href="{prefix}/auth/')
    # Append ?v= to the two main assets so any version bump busts the browser cache
    html = html.replace('/static/app.js"',   f'/static/app.js?v={APP_VERSION}"')
    html = html.replace('/static/style.css"', f'/static/style.css?v={APP_VERSION}"')
    inject = f'<script>window.INGRESS_PREFIX="{prefix}";window.APP_VERSION="{APP_VERSION}";</script>'
    html = html.replace("</head>", inject + "</head>")
    return HTMLResponse(html)

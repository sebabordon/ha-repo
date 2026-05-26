import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from routes import upload, gastos, rules, stats, auth, cuentas, presupuesto, admin, config_route, charts
from routes import scrapers as scrapers_routes
from db import init_db
from config import APP_VERSION
from scraper_scheduler import start_scheduler
import userctx

app = FastAPI(title="Gastos", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def on_startup():
    init_db()          # inicializa la DB raíz (fuente de migraciones)
    start_scheduler()  # arranca scrapers programados (no-op si no hay scrapers.yaml)


# ── Per-user data context middleware ─────────────────────────────────────────
# Tracks which users have already had init_db() run this process lifetime so
# we don't repeat the (cheap but non-zero) work on every request.
_initialized_users: set[str] = set()


@app.middleware("http")
async def user_data_context(request: Request, call_next):
    """Set the per-user data directory for the duration of each request."""
    user = request.session.get("user")
    token = None
    if user and user.get("email"):
        email = user["email"]
        token = userctx.set_user_context(email)
        if email not in _initialized_users:
            init_db()  # create/migrate tables in this user's DB
            _initialized_users.add(email)
    try:
        response = await call_next(request)
    finally:
        if token is not None:
            userctx.reset_user_context(token)
    return response

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "changeme-in-prod"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/auth", tags=["auth"])
app.include_router(upload.router,     prefix="/api",  tags=["upload"])
app.include_router(gastos.router,     prefix="/api",  tags=["gastos"])
app.include_router(rules.router,      prefix="/api",  tags=["rules"])
app.include_router(stats.router,      prefix="/api",  tags=["stats"])
app.include_router(cuentas.router,    prefix="/api",  tags=["cuentas"])
app.include_router(presupuesto.router,  prefix="/api",   tags=["presupuesto"])
app.include_router(config_route.router, prefix="/api",   tags=["config"])
app.include_router(charts.router,          prefix="/api",   tags=["charts"])
app.include_router(scrapers_routes.router, prefix="/api",   tags=["scrapers"])
app.include_router(admin.router,           prefix="/admin", tags=["admin"])

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
        "name":             "Gastos",
        "short_name":       "Gastos",
        "description":      "Gestor de gastos de tarjetas",
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
    title = label.strip() or fuente.upper().replace("_", " ") or "Gasto rápido"
    with open("static/quick.html") as f:
        html = f.read()
    html = html.replace("<title>Gasto Rápido</title>", f"<title>{title}</title>")
    html = html.replace(
        'content="Gastos"',
        f'content="{title}"',
        1,  # solo el primer apple-mobile-web-app-title
    )
    return HTMLResponse(html)


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


def _redirect(request: Request, path: str, status_code: int = 307) -> RedirectResponse:
    prefix = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(f"{prefix}{path}", status_code=status_code)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return _redirect(request, "/auth/login")
    prefix = request.headers.get("X-Ingress-Path", "")
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

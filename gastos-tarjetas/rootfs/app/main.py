import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from routes import upload, gastos, rules, stats, auth, cuentas, presupuesto, admin, config_route, charts
from db import init_db
from config import APP_VERSION
import userctx

app = FastAPI(title="Gastos", docs_url=None, redoc_url=None)


@app.on_event("startup")
def on_startup():
    init_db()  # initialise the root-level DB (used as migration source)


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
app.include_router(charts.router,       prefix="/api",   tags=["charts"])
app.include_router(admin.router,        prefix="/admin", tags=["admin"])

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/manifest.json")
async def serve_manifest():
    """PWA manifest — served from root so scope covers the whole app."""
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


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

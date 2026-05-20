import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from routes import upload, gastos, rules, auth
from db import init_db

app = FastAPI(title="Gastos Tarjetas", docs_url=None, redoc_url=None)


@app.on_event("startup")
def on_startup():
    init_db()

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

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(gastos.router, prefix="/api", tags=["gastos"])
app.include_router(rules.router, prefix="/api", tags=["rules"])

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/auth/login")
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")

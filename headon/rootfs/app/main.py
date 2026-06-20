import io
import json
import os
import secrets
from datetime import date, datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import db
from auth import router as auth_router, admin_router, is_session_token_valid
from openpyxl import Workbook

APP_VERSION = "0.1.0"
DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _load_session_secret() -> str:
    secret_file = os.path.join(DATA_DIR, "session_secret")
    try:
        with open(secret_file) as f:
            secret = f.read().strip()
        if secret:
            return secret
    except FileNotFoundError:
        pass
    secret = secrets.token_urlsafe(48)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(secret_file, "w") as f:
        f.write(secret)
    os.chmod(secret_file, 0o600)
    return secret


app = FastAPI(title="HeadOn", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def on_startup():
    db.init_db()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/auth/") or path.startswith("/static/") or path in ("/manifest.json",):
        return await call_next(request)
    user = request.session.get("user")
    if user and user.get("email"):
        if not is_session_token_valid(user["email"], user.get("stoken", "")):
            request.session.clear()
            user = None
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "No autenticado"}, status_code=401)
        prefix = request.headers.get("X-Ingress-Path", "")
        return RedirectResponse(f"{prefix}/auth/login")
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=_load_session_secret(),
    same_site="lax",
    https_only=False,
    max_age=14 * 24 * 3600,
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return FileResponse("static/index.html")


@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "HeadOn",
        "short_name": "HeadOn",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0f2f5",
        "theme_color": "#16213e",
        "icons": [
            {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}
        ]
    })


@app.get("/api/version")
async def version():
    return {"version": APP_VERSION}


@app.get("/api/me")
async def api_me(request: Request):
    user = request.session.get("user")
    return {"email": user.get("email", ""), "is_admin": user.get("is_admin", False)}


@app.get("/api/migraines")
async def api_list(limit: int = 50, offset: int = 0,
                   fecha_desde: str = None, fecha_hasta: str = None):
    rows = db.list_migraines(limit, offset, fecha_desde, fecha_hasta)
    for r in rows:
        if r.get("localizacion"):
            try:
                r["localizacion"] = json.loads(r["localizacion"])
            except (json.JSONDecodeError, TypeError):
                r["localizacion"] = []
    return rows


@app.post("/api/migraines")
async def api_create(req: Request):
    data = await req.json()
    mid = db.create_migraine(data)
    return {"id": mid}


@app.put("/api/migraines/{mid}")
async def api_update(mid: int, req: Request):
    data = await req.json()
    db.update_migraine(mid, data)
    return {"ok": True}


@app.post("/api/migraines/{mid}/finish")
async def api_finish(mid: int):
    now = datetime.now().strftime("%H:%M")
    db.update_migraine(mid, {"fin": now})
    return {"ok": True, "fin": now}


@app.delete("/api/migraines/{mid}")
async def api_delete(mid: int):
    db.delete_migraine(mid)
    return {"ok": True}


@app.get("/api/calendar/{year}/{month}")
async def api_calendar(year: int, month: int):
    return db.get_calendar_data(year, month)


@app.get("/api/export")
async def api_export(fecha_desde: str = None, fecha_hasta: str = None):
    rows = db.list_migraines(9999, 0, fecha_desde, fecha_hasta)
    wb = Workbook()
    ws = wb.active
    ws.title = "Migrañas"
    headers = ["Fecha", "Inicio", "Fin", "Duración", "Intensidad",
               "Localización", "Tipo Dolor", "Aura", "Medicación", "Comentarios"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    for r in rows:
        loc = r.get("localizacion", "")
        if loc:
            try:
                loc = ", ".join(json.loads(loc))
            except (json.JSONDecodeError, TypeError):
                pass
        dur = ""
        if r.get("inicio"):
            fin = r.get("fin") or "23:59"
            try:
                t0 = datetime.strptime(r["inicio"], "%H:%M")
                t1 = datetime.strptime(fin, "%H:%M")
                mins = int((t1 - t0).total_seconds() / 60)
                if mins >= 0:
                    dur = f"{mins // 60}h {mins % 60}m"
            except ValueError:
                pass
        ws.append([
            r.get("fecha", ""), r.get("inicio", ""), r.get("fin", ""), dur,
            r.get("intensidad", ""), loc, r.get("tipo_dolor", ""),
            "Sí" if r.get("aura") else "No",
            r.get("medicacion", ""), r.get("comentarios", ""),
        ])
    for col in ws.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    today = date.today().isoformat()
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="headon_{today}.xlsx"'}
    )


@app.get("/api/config/{key}")
async def api_get_config(key: str):
    val = db.get_config(key)
    return {"key": key, "value": val}


@app.put("/api/config/{key}")
async def api_set_config(key: str, req: Request):
    data = await req.json()
    db.set_config(key, data.get("value", ""))
    return {"ok": True}


@app.post("/api/sync")
async def api_sync(req: Request):
    """Recibe un batch de operaciones offline y las aplica."""
    ops = await req.json()
    results = []
    for op in ops:
        action = op.get("action")
        data = op.get("data", {})
        try:
            if action == "create":
                mid = db.create_migraine(data)
                results.append({"ok": True, "id": mid, "tempId": op.get("tempId")})
            elif action == "update":
                db.update_migraine(op["id"], data)
                results.append({"ok": True, "id": op["id"]})
            elif action == "delete":
                db.delete_migraine(op["id"])
                results.append({"ok": True, "id": op["id"]})
            elif action == "finish":
                db.update_migraine(op["id"], {"fin": data.get("fin", datetime.now().strftime("%H:%M"))})
                results.append({"ok": True, "id": op["id"]})
        except Exception as e:
            results.append({"ok": False, "error": str(e), "tempId": op.get("tempId")})
    return results

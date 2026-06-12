"""
Web Push (VAPID) — suscripciones del navegador y envío de notificaciones.

Claves VAPID: se generan una vez y se persisten en /data/vapid.json (global,
fuera de las DB de usuario). La pública se expone como applicationServerKey; la
privada firma cada push.

Suscripciones: tabla push_subscriptions per-usuario (en su gastos.db). El
contexto de usuario (middleware) ya apunta _conn() a la DB correcta, así que
las lecturas/escrituras de suscripciones son automáticamente del usuario activo.
"""
import base64
import json
import logging
import os

from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool

from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR   = os.environ.get("DATA_DIR", "/data")
_VAPID_FILE = os.path.join(_DATA_DIR, "vapid.json")
# Claim "sub" de VAPID: contacto del emisor (mailto: o https:). Apple/Safari es
# estricto y rechaza valores tipo "localhost", así que se deriva del
# allowed_domain (ya configurable) → mailto:admin@<dominio>. Override por env.
def _default_vapid_sub() -> str:
    try:
        from config import ALLOWED_DOMAIN
        if ALLOWED_DOMAIN:
            return f"mailto:admin@{ALLOWED_DOMAIN}"
    except Exception:
        pass
    return "mailto:admin@example.com"

_VAPID_SUB = os.environ.get("VAPID_SUB") or _default_vapid_sub()


# ── Claves VAPID ──────────────────────────────────────────────────────────────

def _generate_vapid() -> dict:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    raw_pub = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
    return {"private_pem": priv_pem, "public_key": pub_b64}


def get_vapid() -> dict:
    """Lee (o genera y persiste atómicamente) el par de claves VAPID global."""
    try:
        with open(_VAPID_FILE) as f:
            data = json.load(f)
        if data.get("private_pem") and data.get("public_key"):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    data = _generate_vapid()
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = _VAPID_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _VAPID_FILE)
    except OSError as exc:
        logger.warning("[push] no se pudo persistir vapid.json: %s", exc)
    return data


# ── Suscripciones (tabla per-usuario) ─────────────────────────────────────────

def _save_subscription(sub: dict, ua: str = "") -> None:
    from db import _conn
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth   = keys.get("auth")
    if not (endpoint and p256dh and auth):
        raise ValueError("subscription incompleta")
    with _conn() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (endpoint, p256dh, auth, ua) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(endpoint) DO UPDATE SET "
            "  p256dh=excluded.p256dh, auth=excluded.auth, ua=excluded.ua",
            (endpoint, p256dh, auth, (ua or "")[:200]),
        )


def list_subscriptions() -> list[dict]:
    """Suscripciones del usuario en contexto, en el formato que espera pywebpush."""
    from db import _conn
    with _conn() as conn:
        rows = conn.execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions"
        ).fetchall()
    return [
        {"endpoint": r["endpoint"],
         "keys": {"p256dh": r["p256dh"], "auth": r["auth"]}}
        for r in rows
    ]


def _remove_subscription(endpoint: str) -> None:
    from db import _conn
    with _conn() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))


def _clear_subscriptions() -> int:
    """Borra TODAS las suscripciones del usuario en contexto. Devuelve cuántas."""
    from db import _conn
    with _conn() as conn:
        cur = conn.execute("DELETE FROM push_subscriptions")
        return cur.rowcount if (cur.rowcount or 0) > 0 else 0


# ── Envío ─────────────────────────────────────────────────────────────────────

def send_push(subscriptions: list[dict], title: str, body: str, url: str = "/") -> tuple[int, list[str]]:
    """
    Envía un push a cada suscripción dada. Función pura (recibe las subs
    explícitas), para poder correr en un threadpool sin depender del ContextVar
    de userctx. Devuelve (enviados_ok, endpoints_muertos) — los muertos (404/410)
    los borra el llamador, que sí tiene contexto.
    """
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid01
    v = get_vapid()
    payload = json.dumps({"title": title, "body": body, "url": url})
    ok = 0
    dead: list[str] = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=Vapid01.from_pem(v["private_pem"].encode()),
                vapid_claims={"sub": _VAPID_SUB},
                timeout=10,
            )
            ok += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
            if status in (404, 410):
                dead.append(sub["endpoint"])  # suscripción expirada/cancelada
            logger.warning("[push] envío falló (status=%s): %s", status, str(exc)[:200])
        except Exception as exc:  # errores de red u otros
            logger.warning("[push] envío falló: %s", str(exc)[:200])
    return ok, dead


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/push/public-key")
async def push_public_key(request: Request):
    require_auth(request)
    return {"public_key": get_vapid()["public_key"]}


@router.post("/push/subscribe")
async def push_subscribe(request: Request):
    require_auth(request)
    body = await request.json()
    try:
        _save_subscription(body, request.headers.get("user-agent", ""))
    except ValueError:
        raise HTTPException(400, "Suscripción inválida.")
    return {"ok": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(request: Request):
    require_auth(request)
    body = await request.json()
    endpoint = (body or {}).get("endpoint")
    if endpoint:
        _remove_subscription(endpoint)
    return {"ok": True}


@router.post("/push/clear")
async def push_clear(request: Request):
    """Borra todas las suscripciones del usuario (para limpiar duplicadas)."""
    require_auth(request)
    return {"ok": True, "cleared": _clear_subscriptions()}


@router.post("/push/test")
async def push_test(request: Request):
    require_auth(request)
    subs = list_subscriptions()                       # leído en contexto del request
    if not subs:
        raise HTTPException(400, "No hay suscripciones activas en este dispositivo.")
    ok, dead = await run_in_threadpool(
        send_push, subs, "Finance Me",
        "🔔 Notificaciones activadas correctamente.", "/",
    )
    for ep in dead:
        _remove_subscription(ep)                        # borrado en contexto
    if ok == 0:
        raise HTTPException(502, "El envío falló (revisá el log).")
    return {"ok": True, "sent": ok}

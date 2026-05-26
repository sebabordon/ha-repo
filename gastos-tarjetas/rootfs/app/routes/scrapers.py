"""
Endpoints de scrapers y conciliación.

GET  /api/scrapers/status                 → estado de todos los scrapers
GET  /api/scrapers/jobs                   → jobs programados del scheduler
POST /api/scrapers/{banco}/run            → trigger manual de un scraper
GET  /api/scrapers/pendientes             → movimientos_raw 'unmatched'
POST /api/scrapers/pendientes/{id}/importar  → importar a gastos
POST /api/scrapers/pendientes/{id}/ignorar   → marcar como ignored
POST /api/scrapers/galicia/session-setup  → iniciar flujo TOTP Galicia
POST /api/scrapers/galicia/totp           → enviar código TOTP
GET  /api/scrapers/config-status          → si scrapers.yaml existe y tiene config
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class TotpRequest(BaseModel):
    request_id: str
    code: str


class ImportarRequest(BaseModel):
    categoria: Optional[str] = None


# ── Estado de scrapers ─────────────────────────────────────────────────────────

@router.get("/scrapers/status")
def scrapers_status(request: Request):
    require_auth(request)
    from scrapers_db import get_scraper_statuses, count_pendientes_por_fuente
    statuses  = get_scraper_statuses()
    pendientes = count_pendientes_por_fuente()
    # Enriquecer con count de pendientes
    for s in statuses:
        s["pendientes"] = pendientes.get(s["fuente"], 0)
    return statuses


@router.get("/scrapers/jobs")
def scrapers_jobs(request: Request):
    require_auth(request)
    from scraper_scheduler import get_scheduler_jobs
    return get_scheduler_jobs()


@router.get("/scrapers/config-status")
def scrapers_config_status(request: Request):
    require_auth(request)
    from scrapers_config import is_configured, get_all_enabled_scrapers
    enabled = get_all_enabled_scrapers()
    return {
        "configured": is_configured(),
        "bancos_habilitados": list(enabled.keys()),
    }


# ── Trigger manual ─────────────────────────────────────────────────────────────

@router.post("/scrapers/{banco}/run")
async def run_scraper(banco: str, request: Request):
    require_auth(request)
    valid = ("amex", "bbva", "galicia", "mercadopago")
    if banco not in valid:
        raise HTTPException(400, f"Banco inválido. Opciones: {valid}")

    from scraper_scheduler import run_scraper_now
    result = await run_scraper_now(banco)

    if not result.get("ok"):
        status_code = 503 if result.get("session_expired") else 500
        raise HTTPException(status_code, result.get("error", "Error desconocido"))

    return result


# ── Movimientos pendientes de conciliación ────────────────────────────────────

@router.get("/scrapers/pendientes")
def get_pendientes(
    request: Request,
    fuente: Optional[str] = None,
    limit: int = 200,
):
    require_auth(request)
    from scrapers_db import list_movimientos_raw
    rows = list_movimientos_raw(estado="unmatched", fuente=fuente, limit=limit)
    return rows


@router.get("/scrapers/movimientos-raw")
def get_movimientos_raw(
    request: Request,
    estado: Optional[str] = None,
    fuente: Optional[str] = None,
    limit: int = 500,
):
    """Todos los movimientos_raw (para debug / vista completa)."""
    require_auth(request)
    from scrapers_db import list_movimientos_raw
    return list_movimientos_raw(estado=estado, fuente=fuente, limit=limit)


@router.post("/scrapers/pendientes/{raw_id}/importar")
def importar_pendiente(raw_id: int, body: ImportarRequest, request: Request):
    require_auth(request)
    from scrapers_db import importar_a_gastos, get_movimiento_raw
    raw = get_movimiento_raw(raw_id)
    if not raw:
        raise HTTPException(404, f"Movimiento raw {raw_id} no encontrado")
    if raw["estado"] not in ("unmatched", "new"):
        raise HTTPException(409, f"El movimiento está en estado '{raw['estado']}', no se puede importar")

    new_id = importar_a_gastos(raw_id, categoria=body.categoria)
    if new_id is None:
        raise HTTPException(409, "No se pudo importar (ya procesado o no encontrado)")

    # Aplicar categorización automática al nuevo gasto
    try:
        from categorizer import categorize
        from db import update_categoria
        cat = categorize(raw["descripcion"])
        if cat:
            update_categoria(new_id, cat)
    except Exception as exc:
        logger.warning("Error al categorizar gasto importado: %s", exc)

    return {"ok": True, "gasto_id": new_id}


@router.post("/scrapers/pendientes/{raw_id}/ignorar")
def ignorar_pendiente(raw_id: int, request: Request):
    require_auth(request)
    from scrapers_db import update_movimiento_raw, get_movimiento_raw
    raw = get_movimiento_raw(raw_id)
    if not raw:
        raise HTTPException(404, f"Movimiento raw {raw_id} no encontrado")
    update_movimiento_raw(raw_id, "ignored")
    return {"ok": True}


# ── Conciliación manual ────────────────────────────────────────────────────────

@router.post("/scrapers/conciliar")
def run_conciliacion(request: Request, fuente: Optional[str] = None):
    """Re-corre la conciliación sobre todos los movimientos 'new'."""
    require_auth(request)
    from conciliacion import run_conciliation
    result = run_conciliation(fuente=fuente)
    return result


# ── Galicia: flujo TOTP ────────────────────────────────────────────────────────

@router.post("/scrapers/galicia/session-setup")
async def galicia_session_setup(request: Request):
    """
    Inicia el flujo interactivo de sesión Galicia.
    El browser hace login hasta la pantalla de TOTP y espera.
    Devuelve request_id para enviarlo con el código.
    """
    require_auth(request)
    from scrapers_config import get_scraper_config
    config = get_scraper_config("galicia")
    if not config:
        raise HTTPException(400, "Galicia no está habilitado en scrapers.yaml")

    from scrapers.galicia import GaliciaScraper
    scraper    = GaliciaScraper()
    request_id = await scraper.start_session_setup(config)

    return {
        "status":     "waiting_totp",
        "request_id": request_id,
        "message":    "El browser está esperando el código TOTP. "
                      "Revisá tu mail o app de Galicia y enviá el código.",
    }


@router.post("/scrapers/galicia/totp")
async def galicia_totp(body: TotpRequest, request: Request):
    """Envía el código TOTP al browser que está esperando."""
    require_auth(request)
    from scrapers.galicia import GaliciaScraper
    scraper = GaliciaScraper()
    ok      = await scraper.submit_totp_code(body.request_id, body.code)
    if not ok:
        raise HTTPException(404, "No hay sesión pendiente con ese request_id (¿ya expiró?)")
    return {"status": "code_submitted", "message": "Código enviado. La sesión se guardará en segundos."}


@router.delete("/scrapers/{banco}/session")
def delete_session(banco: str, request: Request):
    """Elimina la sesión guardada de un banco (fuerza re-login en el próximo run)."""
    require_auth(request)
    valid = ("amex", "bbva", "galicia", "mercadopago")
    if banco not in valid:
        raise HTTPException(400, f"Banco inválido. Opciones: {valid}")

    import os
    from scrapers.base import _SESSIONS_DIR
    session_path = os.path.join(_SESSIONS_DIR, f"{banco}.json")
    if os.path.exists(session_path):
        os.remove(session_path)
        return {"ok": True, "message": f"Sesión de {banco} eliminada."}
    return {"ok": True, "message": "No había sesión guardada."}

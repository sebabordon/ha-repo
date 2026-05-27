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
GET  /api/scrapers/config-status          → si hay scrapers configurados
GET  /api/scrapers/credentials            → credenciales del usuario (passwords ocultos)
PUT  /api/scrapers/credentials/{banco}    → guardar/actualizar credenciales de un banco
GET  /api/scrapers/banks                  → definición de bancos (campos, labels, etc.)
POST /api/scrapers/scheduler/reload       → recargar el scheduler tras guardar credenciales
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


class MovimientoRapidoRequest(BaseModel):
    fuente: str
    fecha: str
    descripcion: str = ""
    monto: float
    moneda: str = "ARS"
    categoria: Optional[str] = None
    tipo: str = "egreso"  # "egreso" | "ingreso"


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
    from scraper_credentials import find_all_enabled_configs, creds_for_api
    configs  = find_all_enabled_configs()
    enabled  = list({e["banco"] for e in configs})
    api_data = creds_for_api()   # usa el data_dir del usuario logueado
    user_enabled = [b for b, v in api_data.items() if v.get("enabled")]
    return {
        "configured":        bool(enabled or user_enabled),
        "bancos_habilitados": user_enabled,
    }


# ── Credenciales por usuario ───────────────────────────────────────────────────

@router.get("/scrapers/banks")
def get_banks_definition(request: Request):
    """Devuelve la definición estática de bancos (campos, labels, etc.)."""
    require_auth(request)
    from scraper_credentials import BANKS
    # Devolver solo metadatos, sin datos de usuario
    return {
        banco: {
            "nombre": defn["nombre"],
            "schedule_default": defn["schedule"],
            "totp": defn.get("totp", False),
            "campos": defn["campos"],
        }
        for banco, defn in BANKS.items()
    }


@router.get("/scrapers/credentials")
def get_credentials(request: Request):
    """
    Devuelve la configuración de scrapers del usuario logueado.
    Los campos de tipo 'password' siempre vienen vacíos; se indica si hay
    una contraseña guardada con 'has_password': true.
    """
    require_auth(request)
    from scraper_credentials import creds_for_api
    return creds_for_api()


@router.put("/scrapers/credentials/{banco}")
async def put_credentials(banco: str, body: dict, request: Request):
    """
    Guarda/actualiza las credenciales de un banco para el usuario logueado.
    Si un campo de contraseña viene vacío, se mantiene el valor existente.
    Después de guardar recarga el scheduler para aplicar los cambios.

    Debe ser async: AsyncIOScheduler.start() llama a asyncio.get_running_loop()
    y necesita estar en el event loop (no en un thread pool).
    """
    require_auth(request)
    from scraper_credentials import BANKS, set_bank_config
    from scraper_scheduler import reload_scheduler

    if banco not in BANKS:
        raise HTTPException(400, f"Banco desconocido: {banco}. Opciones: {list(BANKS)}")

    # Validar formato HH:MM del schedule
    if "schedule" in body:
        import re
        if not re.match(r"^\d{1,2}:\d{2}$", str(body["schedule"])):
            raise HTTPException(400, "schedule debe tener formato HH:MM")

    set_bank_config(banco, body)
    reload_scheduler()

    return {"ok": True, "banco": banco}


@router.post("/scrapers/scheduler/reload")
async def scheduler_reload(request: Request):
    """Recarga el scheduler (útil tras editar credenciales desde otra interfaz)."""
    require_auth(request)
    from scraper_scheduler import reload_scheduler
    reload_scheduler()
    return {"ok": True}


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

    # Aplicar categorización automática al nuevo gasto (solo reglas, sync-safe)
    try:
        from categorizer import categorize_by_rules
        from db import update_categoria
        cat = categorize_by_rules(raw["descripcion"])
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


@router.post("/scrapers/{banco}/importar-pendientes")
def importar_pendientes_banco(banco: str, request: Request):
    """
    Importa a gastos todos los movimientos_raw 'unmatched' del banco.
    Útil para importar lotes previos al auto-import automático.
    """
    require_auth(request)
    from scrapers_db import auto_import_unmatched
    n = auto_import_unmatched(banco)
    return {"ok": True, "imported": n}


@router.delete("/scrapers/movimientos-raw/{raw_id}")
def delete_raw_movimiento(raw_id: int, request: Request):
    """
    Borra un movimiento_raw. Si estaba en estado 'imported' también elimina
    el gasto asociado de la tabla gastos.
    """
    require_auth(request)
    from scrapers_db import delete_movimiento_raw
    result = delete_movimiento_raw(raw_id)
    if not result["deleted_raw"]:
        raise HTTPException(404, f"Movimiento raw {raw_id} no encontrado")
    return {"ok": True, **result}


# ── Movimiento rápido (desde shortcut PWA) ───────────────────────────────────

@router.post("/movimientos-rapidos")
def crear_movimiento_rapido(body: MovimientoRapidoRequest, request: Request):
    """
    Inserta un movimiento en movimientos_raw con estado='new', corre
    conciliación y, si queda 'unmatched', lo importa automáticamente a gastos.
    """
    require_auth(request)
    from scrapers_db import insert_movimiento_raw_single, get_movimiento_raw, importar_a_gastos
    from conciliacion import run_conciliation

    # Signo: egreso = positivo, ingreso = negativo
    monto = abs(body.monto) if body.tipo == "egreso" else -abs(body.monto)
    desc  = body.descripcion.strip() or f"Movimiento {body.fuente}"

    raw_data: dict = {"manual_quick": True}
    if body.categoria:
        raw_data["categoria"] = body.categoria

    raw_id = insert_movimiento_raw_single({
        "fuente":      body.fuente,
        "fecha":       body.fecha,
        "descripcion": desc,
        "monto":       monto,
        "moneda":      body.moneda,
        "raw_data":    raw_data,
    })

    # Conciliar — puede matchear con un PDF ya importado
    run_conciliation(fuente=body.fuente)

    # Si sigue sin match, importar directamente a gastos
    gasto_id = None
    raw = get_movimiento_raw(raw_id)
    if raw and raw["estado"] == "unmatched":
        cat = body.categoria
        if not cat:
            try:
                from categorizer import categorize_by_rules
                cat = categorize_by_rules(desc)
            except Exception:
                pass
        gasto_id = importar_a_gastos(raw_id, categoria=cat, archivo_origen="manual")
        if gasto_id and cat:
            try:
                from db import update_categoria
                update_categoria(gasto_id, cat)
            except Exception:
                pass

    return {"ok": True, "raw_id": raw_id, "gasto_id": gasto_id}


# ── Conciliación manual ────────────────────────────────────────────────────────

@router.post("/scrapers/conciliar")
def run_conciliacion(request: Request, fuente: Optional[str] = None):
    """Re-corre la conciliación sobre todos los movimientos 'new'."""
    require_auth(request)
    from conciliacion import run_conciliation
    result = run_conciliation(fuente=fuente)
    return result


# ── Flujo TOTP (Galicia y cualquier banco con totp=True) ─────────────────────

@router.post("/scrapers/{banco}/session-setup")
async def banco_session_setup(banco: str, request: Request):
    """
    Inicia el flujo interactivo de sesión con TOTP para un banco.
    Actualmente solo Galicia lo usa, pero la arquitectura lo soporta genéricamente.
    """
    require_auth(request)
    from scraper_credentials import get_bank_config, BANKS
    bank_def = BANKS.get(banco, {})
    if not bank_def.get("totp"):
        raise HTTPException(400, f"{banco} no usa flujo TOTP interactivo.")

    config = get_bank_config(banco)
    if not config:
        raise HTTPException(400, f"{banco} no está habilitado. Configurá las credenciales primero.")

    # Cargar el scraper correspondiente
    from scraper_scheduler import _load_scraper
    scraper = _load_scraper(banco)
    if not hasattr(scraper, "start_session_setup"):
        raise HTTPException(500, f"El scraper de {banco} no implementa start_session_setup.")

    request_id = await scraper.start_session_setup(config)
    return {
        "status":     "waiting_totp",
        "request_id": request_id,
        "message":    "El browser está esperando el código. Ingresalo en la UI.",
    }


@router.post("/scrapers/{banco}/totp")
async def banco_totp(banco: str, body: TotpRequest, request: Request):
    """Envía el código TOTP al browser que está esperando."""
    require_auth(request)
    from scraper_scheduler import _load_scraper
    scraper = _load_scraper(banco)
    if not hasattr(scraper, "submit_totp_code"):
        raise HTTPException(500, f"El scraper de {banco} no implementa submit_totp_code.")
    ok = await scraper.submit_totp_code(body.request_id, body.code)
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

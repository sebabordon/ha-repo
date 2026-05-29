"""
Endpoints REST para las scraper_instances (v0.4.1+).

Pensados para la UI de la tab Cuentas: cada cuenta auto puede elegir una
instancia (combo) y editar inline sus credenciales, correr-now, ver log y
movimientos guardados.

Los endpoints viejos `/api/scrapers/...` siguen vivos para back-compat con la
tab Scrapers vieja — operan sobre la instancia "default" de cada banco.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth import require_auth

router = APIRouter()


_SECRET_FIELDS_BY_BANCO: dict[str, set[str]] = {}


def _secret_keys_for(banco: str) -> set[str]:
    """Devuelve los campos type=password definidos para este banco en BANKS."""
    if banco in _SECRET_FIELDS_BY_BANCO:
        return _SECRET_FIELDS_BY_BANCO[banco]
    try:
        from scraper_credentials import BANKS
        bank_def = BANKS.get(banco, {})
        secrets = {f["key"] for f in bank_def.get("campos", []) if f.get("type") == "password"}
    except Exception:
        secrets = set()
    _SECRET_FIELDS_BY_BANCO[banco] = secrets
    return secrets


def _strip_secrets(config: dict, banco: str) -> dict:
    """Saca contraseñas de la config; marca con has_<key> si estaba presente."""
    secrets = _secret_keys_for(banco)
    out = {}
    for k, v in (config or {}).items():
        if k in secrets:
            out[f"has_{k}"] = bool(v)
        else:
            out[k] = v
    return out


def _merge_config_preserving_secrets(existing: dict, new: dict, banco: str) -> dict:
    """
    Mergea config nueva sobre existente, preservando passwords si llegan vacíos
    (igual lógica que el set_bank_config legacy).
    """
    secrets = _secret_keys_for(banco)
    merged = dict(existing or {})
    for k, v in (new or {}).items():
        if k in secrets and not v:
            continue   # vacío → mantener password existente
        merged[k] = v
    return merged


# ── GET /scraper-types ────────────────────────────────────────────────────────

@router.get("/scraper-types")
def list_scraper_types(request: Request):
    """
    Devuelve los tipos de scraper disponibles (BBVA/AMEX/Galicia/MP) con su
    definición de campos.  Usado por el combo de la tab Cuentas para mostrar
    "+ Nueva instancia <Banco>".
    """
    require_auth(request)
    from scraper_credentials import BANKS
    return [
        {"banco": banco, "nombre": d.get("nombre", banco),
         "schedule_default": d.get("schedule", "07:00"),
         "campos": d.get("campos", []),
         "totp": bool(d.get("totp"))}
        for banco, d in BANKS.items()
    ]


# ── GET /scraper-instances ────────────────────────────────────────────────────

@router.get("/scraper-instances")
def list_instances_route(request: Request, banco: Optional[str] = None):
    """Lista las instancias del usuario actual (con secretos enmascarados)."""
    require_auth(request)
    from scraper_instances_db import list_instances
    insts = list_instances(banco=banco)
    out = []
    for i in insts:
        i_safe = dict(i)
        i_safe["config"] = _strip_secrets(i.get("config") or {}, i["banco"])
        out.append(i_safe)
    return out


# ── GET /scraper-instances/{id} ───────────────────────────────────────────────

@router.get("/scraper-instances/{instance_id}")
def get_instance_route(instance_id: int, request: Request):
    require_auth(request)
    from scraper_instances_db import get_instance, get_cuentas_for_instance
    inst = get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instancia {instance_id} no encontrada")
    inst["config"] = _strip_secrets(inst.get("config") or {}, inst["banco"])
    inst["cuentas"] = get_cuentas_for_instance(instance_id)
    return inst


# ── POST /scraper-instances ───────────────────────────────────────────────────

@router.post("/scraper-instances")
async def create_instance_route(body: dict, request: Request):
    """
    Crea una nueva instancia.
    Body: { banco, nombre, config (opcional), schedule (opcional), enabled (opcional),
            cuenta_fuente (opcional — si se pasa, también linkea la cuenta),
            product_key (opcional, default 'main' para single-product) }
    """
    require_auth(request)
    from scraper_credentials import BANKS
    from scraper_instances_db import create_instance, link_cuenta
    from scraper_scheduler import reload_scheduler

    banco = (body.get("banco") or "").strip()
    nombre = (body.get("nombre") or "").strip()
    if banco not in BANKS:
        raise HTTPException(400, f"banco inválido: {banco!r}. Opciones: {list(BANKS)}")
    if not nombre:
        raise HTTPException(400, "nombre requerido")

    config = body.get("config") or {}
    schedule = body.get("schedule") or BANKS[banco].get("schedule", "07:00")
    enabled = bool(body.get("enabled", True))

    instance_id = create_instance(
        banco=banco, nombre=nombre, config=config,
        schedule=schedule, enabled=enabled,
    )

    # Linkeo opcional a una cuenta existente
    cuenta_fuente = (body.get("cuenta_fuente") or "").strip()
    product_key = (body.get("product_key") or "main").strip() or "main"
    if cuenta_fuente:
        link_cuenta(cuenta_fuente, instance_id, product_key)

    reload_scheduler()
    return {"ok": True, "instance_id": instance_id}


# ── PUT /scraper-instances/{id} ───────────────────────────────────────────────

@router.put("/scraper-instances/{instance_id}")
async def update_instance_route(instance_id: int, body: dict, request: Request):
    """
    Actualiza una instancia (nombre, config, schedule, enabled).
    Para `config`: hace merge preservando contraseñas si llegan vacías.
    """
    require_auth(request)
    from scraper_instances_db import get_instance, update_instance
    from scraper_scheduler import reload_scheduler

    inst = get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instancia {instance_id} no encontrada")

    new_config = None
    if "config" in body:
        merged = _merge_config_preserving_secrets(
            inst.get("config") or {}, body["config"] or {}, inst["banco"],
        )
        new_config = merged

    if "schedule" in body:
        import re
        if body["schedule"] and not re.match(r"^\d{1,2}:\d{2}$", str(body["schedule"])):
            raise HTTPException(400, "schedule debe tener formato HH:MM")

    update_instance(
        instance_id,
        nombre=body.get("nombre") if "nombre" in body else None,
        config=new_config,
        schedule=body.get("schedule") if "schedule" in body else None,
        enabled=bool(body["enabled"]) if "enabled" in body else None,
    )
    reload_scheduler()
    return {"ok": True}


# ── DELETE /scraper-instances/{id} ────────────────────────────────────────────

@router.delete("/scraper-instances/{instance_id}")
async def delete_instance_route(instance_id: int, request: Request):
    require_auth(request)
    from scraper_instances_db import get_instance, delete_instance
    from scraper_scheduler import reload_scheduler

    inst = get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instancia {instance_id} no encontrada")

    delete_instance(instance_id)
    reload_scheduler()
    return {"ok": True}


# ── POST /scraper-instances/{id}/run ──────────────────────────────────────────

@router.post("/scraper-instances/{instance_id}/run")
async def run_instance_route(instance_id: int, request: Request):
    require_auth(request)
    from scraper_scheduler import run_instance_now
    result = await run_instance_now(instance_id)
    return result


# ── PUT /cuentas/{fuente}/scraper ─────────────────────────────────────────────
# Asigna/desasigna una instancia a una cuenta auto.

@router.put("/cuentas/{fuente}/scraper")
def set_cuenta_scraper(fuente: str, body: dict, request: Request):
    """
    Body: { instance_id: int|None, product_key: str|None }
    - instance_id=None → desasigna (cuenta queda sin scraper).
    - instance_id=int  → linkea con el product_key dado (default "main").
    """
    require_auth(request)
    from scraper_instances_db import get_instance, link_cuenta, unlink_cuenta
    from scraper_scheduler import reload_scheduler

    instance_id = body.get("instance_id")
    if instance_id in (None, "", 0, "0"):
        unlink_cuenta(fuente)
        reload_scheduler()
        return {"ok": True, "linked": False}

    try:
        inst_id_int = int(instance_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "instance_id debe ser numérico")

    inst = get_instance(inst_id_int)
    if not inst:
        raise HTTPException(404, f"Instancia {inst_id_int} no encontrada")

    product_key = (body.get("product_key") or "main").strip() or "main"
    link_cuenta(fuente, inst_id_int, product_key)
    reload_scheduler()
    return {"ok": True, "linked": True, "instance_id": inst_id_int,
            "product_key": product_key}

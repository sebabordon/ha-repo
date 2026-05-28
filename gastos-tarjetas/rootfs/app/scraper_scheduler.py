"""
Scheduler de scrapers bancarios (APScheduler + asyncio).

Arranca junto con la app FastAPI. Lee las credenciales por usuario desde
/data/*/scraper_credentials.json y programa un job diario por cada scraper
habilitado.

Cada job setea el user-context de userctx antes de correr para que todas las
operaciones de DB apunten al directorio correcto del usuario.

Integración en main.py:
    from scraper_scheduler import start_scheduler
    @app.on_event("startup")
    async def on_startup():
        init_db()
        start_scheduler()
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None

_SCRAPER_CLASSES = {
    "amex":        "scrapers.amex:AmexScraper",
    "bbva":        "scrapers.bbva:BbvaScraper",
    "galicia":     "scrapers.galicia:GaliciaScraper",
    "mercadopago": "scrapers.mercadopago:MercadoPagoScraper",
}


def _load_scraper(banco: str):
    spec = _SCRAPER_CLASSES.get(banco)
    if not spec:
        raise ValueError(f"Scraper desconocido: {banco}")
    module_path, class_name = spec.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def _email_from_data_dir(data_dir: str) -> str | None:
    """
    Intenta derivar el email del usuario desde su directorio.
    Busca el archivo user_config.json o, si no existe, devuelve None
    (el contexto se establecerá via set_user_dir_context).
    """
    # No hay un archivo de email canónico, pero podemos setear el dir directamente
    return None


async def _run_scraper_job(banco: str, data_dir: str) -> None:
    """
    Job que corre el scraper de un banco en el contexto del usuario dado.
    """
    from scraper_credentials import get_bank_config
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, upsert_scraper_status

    # Setear contexto de usuario para que DB y archivos apunten al dir correcto
    from userctx import _user_data_dir
    token = _user_data_dir.set(data_dir)

    try:
        config = get_bank_config(banco, data_dir)
        if not config:
            logger.info("[scheduler] %s en %s deshabilitado, saltando.", banco, data_dir)
            return

        logger.info("[scheduler] Iniciando scraper: %s (usuario: %s)", banco, data_dir)
        try:
            scraper = _load_scraper(banco)
            result  = await scraper.run(config)
        except Exception as exc:
            logger.exception("[scheduler] Error ejecutando scraper %s: %s", banco, exc)
            upsert_scraper_status(banco, estado="error", error_msg=str(exc))
            return

        if result.error:
            logger.warning("[scheduler] %s terminó con error: %s", banco, result.error)
            return

        emitted_fuentes: set[str] = set()
        if result.movimientos:
            dicts = [m.to_dict() for m in result.movimientos]
            count = insert_movimientos_raw(dicts)
            emitted_fuentes = {d["fuente"] for d in dicts if d.get("fuente")}
            logger.info("[scheduler] %s: %d movimientos insertados (fuentes=%s).",
                        banco, count, sorted(emitted_fuentes))
        else:
            logger.info("[scheduler] %s: sin movimientos nuevos.", banco)

        # Conciliar y auto-importar por CADA fuente emitida.  El "banco" es la
        # clave del scraper (ej. "bbva") pero los movimientos pueden tener una
        # fuente distinta (ej. "bbva_cuenta", "bbva_visa", "bbva_mc") según
        # qué producto del banco generó el dato.
        from scrapers_db import auto_import_unmatched
        for f in (emitted_fuentes or {banco}):
            conc = run_conciliation(fuente=f)
            logger.info("[scheduler] Conciliación %s: %s", f, conc)
            imported = auto_import_unmatched(f)
            if imported:
                logger.info("[scheduler] %s: %d movimientos auto-importados a gastos.", f, imported)

    finally:
        _user_data_dir.reset(token)


def start_scheduler() -> None:
    """
    Escanea /data/*/scraper_credentials.json y programa un job diario
    por cada scraper habilitado. No-op si no hay credenciales configuradas.
    """
    global _scheduler

    from scraper_credentials import find_all_enabled_configs

    configs = find_all_enabled_configs()
    if not configs:
        logger.info(
            "[scheduler] No hay scrapers configurados. "
            "Configurá las credenciales en Config → Scrapers."
        )
        return

    _scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")

    for entry in configs:
        banco    = entry["banco"]
        data_dir = entry["data_dir"]
        cfg      = entry["config"]
        schedule_str = cfg.get("schedule", "07:00")

        try:
            hour, minute = schedule_str.split(":")
        except ValueError:
            logger.warning("[scheduler] Horario inválido para %s: '%s' → 07:00",
                           banco, schedule_str)
            hour, minute = "7", "0"

        job_id = f"scraper_{banco}_{os.path.basename(data_dir)}"
        trigger = CronTrigger(hour=int(hour), minute=int(minute))
        _scheduler.add_job(
            _run_scraper_job,
            trigger=trigger,
            args=[banco, data_dir],
            id=job_id,
            name=f"Scraper {banco}",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "[scheduler] Programado %s @ %s:%s (dir: %s)",
            banco, hour.zfill(2), minute.zfill(2), os.path.basename(data_dir),
        )

    _scheduler.start()
    logger.info("[scheduler] Iniciado con %d jobs.", len(configs))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reload_scheduler() -> None:
    """Recarga los jobs del scheduler (llamar después de guardar credenciales)."""
    stop_scheduler()
    start_scheduler()


async def run_scraper_now(banco: str, data_dir: str | None = None) -> dict:
    """
    Trigger manual de un scraper. Usa el data_dir del usuario actual si no se
    especifica (inferido desde userctx).
    """
    from scraper_credentials import get_bank_config
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, upsert_scraper_status
    from userctx import get_data_dir

    effective_dir = data_dir or get_data_dir()
    config = get_bank_config(banco, effective_dir)
    if not config:
        return {"ok": False, "error": f"'{banco}' no está habilitado. Configurá las credenciales primero."}

    try:
        scraper = _load_scraper(banco)
        result  = await scraper.run(config)
    except Exception as exc:
        msg = f"Error al ejecutar scraper: {exc}"
        logger.exception(msg)
        return {"ok": False, "error": msg}

    if result.error:
        return {"ok": False, "error": result.error, "session_expired": result.session_expired}

    inserted = 0
    emitted_fuentes: set[str] = set()
    if result.movimientos:
        dicts    = [m.to_dict() for m in result.movimientos]
        inserted = insert_movimientos_raw(dicts)
        emitted_fuentes = {d["fuente"] for d in dicts if d.get("fuente")}

    # Conciliar y auto-importar por CADA fuente emitida (no por el "banco"):
    # bbva ejecuta el scraper pero los datos pueden ir a bbva_cuenta / bbva_visa
    # / bbva_mc según el producto.  Sin esta unión, los movimientos quedaban
    # atascados en movimientos_raw con estado='new' (la conciliación buscaba
    # por fuente='bbva' y no encontraba nada).
    from scrapers_db import auto_import_unmatched
    conc_agg = {"matched": 0, "unmatched": 0, "errors": 0}
    auto_imported = 0
    for f in (emitted_fuentes or {banco}):
        c = run_conciliation(fuente=f)
        for k in ("matched", "unmatched", "errors"):
            conc_agg[k] += c.get(k, 0)
        auto_imported += auto_import_unmatched(f)

    return {
        "ok":            True,
        "banco":         banco,
        "movimientos":   inserted,
        "auto_imported": auto_imported,
        "conciliacion":  conc_agg,
        "saldos":        result.saldos,
        "timestamp":     datetime.utcnow().isoformat(),
    }


def get_scheduler_jobs() -> list[dict]:
    if not _scheduler:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        nf = job.next_run_time
        jobs.append({
            "id":       job.id,
            "name":     job.name,
            "next_run": nf.isoformat() if nf else None,
        })
    return jobs

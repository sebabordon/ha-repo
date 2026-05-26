"""
Scheduler de scrapers bancarios (APScheduler + asyncio).

Arranca junto con la app FastAPI. Lee scrapers.yaml y programa un job
diario por cada banco habilitado. También expone funciones para trigger manual.

Integración en main.py:
    from scraper_scheduler import start_scheduler, run_scraper_now
    @app.on_event("startup")
    async def on_startup():
        init_db()
        start_scheduler()
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None

# Registro de scrapers disponibles — se importan aquí para no cargar Playwright
# en el arranque: solo se instancian cuando hay config habilitado.
_SCRAPER_CLASSES = {
    "amex":        "scrapers.amex:AmexScraper",
    "bbva":        "scrapers.bbva:BbvaScraper",
    "galicia":     "scrapers.galicia:GaliciaScraper",
    "mercadopago": "scrapers.mercadopago:MercadoPagoScraper",
}


def _load_scraper(banco: str):
    """Importa e instancia el scraper para un banco dado."""
    spec = _SCRAPER_CLASSES.get(banco)
    if not spec:
        raise ValueError(f"Scraper desconocido: {banco}")
    module_path, class_name = spec.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


async def _run_scraper_job(banco: str) -> None:
    """
    Job que corre el scraper de un banco y luego la conciliación.
    Se ejecuta en el event loop del scheduler.
    """
    from scrapers_config import get_scraper_config
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, upsert_scraper_status

    config = get_scraper_config(banco)
    if not config:
        logger.info("[scheduler] %s deshabilitado, saltando.", banco)
        return

    logger.info("[scheduler] Iniciando scraper: %s", banco)
    try:
        scraper = _load_scraper(banco)
        result  = await scraper.run(config)
    except Exception as exc:
        logger.exception("[scheduler] Error cargando/ejecutando scraper %s: %s", banco, exc)
        upsert_scraper_status(banco, estado="error", error_msg=str(exc))
        return

    if result.error:
        logger.warning("[scheduler] %s terminó con error: %s", banco, result.error)
        return

    # Persistir movimientos en staging
    if result.movimientos:
        dicts = [m.to_dict() for m in result.movimientos]
        count = insert_movimientos_raw(dicts)
        logger.info("[scheduler] %s: %d movimientos insertados en staging.", banco, count)
    else:
        logger.info("[scheduler] %s: 0 movimientos (stub o sin actividad).", banco)

    # Conciliar contra gastos existentes
    conc_result = run_conciliation(fuente=banco)
    logger.info("[scheduler] Conciliación %s: %s", banco, conc_result)


def start_scheduler() -> None:
    """
    Lee scrapers.yaml y programa jobs diarios para cada banco habilitado.
    Debe llamarse una sola vez al arranque de la app.
    """
    global _scheduler

    from scrapers_config import get_all_enabled_scrapers

    enabled = get_all_enabled_scrapers()
    if not enabled:
        logger.info("[scheduler] scrapers.yaml no encontrado o sin scrapers habilitados. "
                    "Crear /data/scrapers.yaml para activar.")
        return

    _scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")

    for banco, cfg in enabled.items():
        schedule_str = cfg.get("schedule", "07:00")
        try:
            hour, minute = schedule_str.split(":")
        except ValueError:
            logger.warning("[scheduler] Horario inválido para %s: '%s' → usando 07:00", banco, schedule_str)
            hour, minute = "7", "0"

        trigger = CronTrigger(hour=int(hour), minute=int(minute))
        _scheduler.add_job(
            _run_scraper_job,
            trigger=trigger,
            args=[banco],
            id=f"scraper_{banco}",
            name=f"Scraper {banco}",
            replace_existing=True,
            misfire_grace_time=3600,  # 1h de gracia si el RPi estaba apagado
        )
        logger.info(
            "[scheduler] Programado %s a las %s:%s (hora AR).",
            banco, hour.zfill(2), minute.zfill(2),
        )

    _scheduler.start()
    logger.info("[scheduler] Scheduler iniciado con %d jobs.", len(enabled))


def stop_scheduler() -> None:
    """Detiene el scheduler (llamar en shutdown de la app si es necesario)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def run_scraper_now(banco: str) -> dict:
    """
    Trigger manual de un scraper. Corre inmediatamente (sin esperar el cron).
    Devuelve dict con el resultado.
    """
    from scrapers_config import get_scraper_config
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, upsert_scraper_status

    config = get_scraper_config(banco)
    if not config:
        return {"ok": False, "error": f"Scraper '{banco}' no está habilitado en scrapers.yaml"}

    try:
        scraper  = _load_scraper(banco)
        result   = await scraper.run(config)
    except Exception as exc:
        msg = f"Error al ejecutar scraper: {exc}"
        logger.exception(msg)
        return {"ok": False, "error": msg}

    if result.error:
        return {"ok": False, "error": result.error, "session_expired": result.session_expired}

    inserted = 0
    if result.movimientos:
        dicts    = [m.to_dict() for m in result.movimientos]
        inserted = insert_movimientos_raw(dicts)

    conc = run_conciliation(fuente=banco)

    return {
        "ok":             True,
        "banco":          banco,
        "movimientos":    inserted,
        "conciliacion":   conc,
        "saldos":         result.saldos,
        "timestamp":      datetime.utcnow().isoformat(),
    }


def get_scheduler_jobs() -> list[dict]:
    """Devuelve info de los jobs programados (para la UI)."""
    if not _scheduler:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        nf = job.next_run_time
        jobs.append({
            "id":           job.id,
            "name":         job.name,
            "next_run":     nf.isoformat() if nf else None,
        })
    return jobs

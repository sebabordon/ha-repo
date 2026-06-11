"""
Scheduler de scrapers bancarios (APScheduler + asyncio).

Arranca junto con la app FastAPI. A partir de v0.4.0 itera la tabla
`scraper_instances` (en la DB del usuario) en lugar del `scraper_credentials.json`.
Cada instancia tiene su propio set de credenciales + schedule + cuentas mapeadas.

Cada job setea el user-context de userctx antes de correr para que todas las
operaciones de DB apunten al directorio correcto del usuario.

Las cuentas mapeadas a una instancia se pasan al scraper vía `config["__cuentas__"]`
para que el scraper sepa a qué `fuente` emitir los movimientos.

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

# Intervalos permitidos (horas).  Deben dividir 24 para que el cron `*/N`
# reparta las corridas de forma uniforme a lo largo del día.
# Mínimo 2h (para no martillar el homebanking), default 4h.
ALLOWED_INTERVAL_HOURS = (2, 3, 4, 6, 8, 12, 24)
DEFAULT_INTERVAL_HOURS = 4
DEFAULT_SCHEDULE = f"every:{DEFAULT_INTERVAL_HOURS}h"


def parse_schedule(schedule_str: str, instance_id: int = 0) -> CronTrigger:
    """
    Convierte el `schedule` de una instancia en un CronTrigger.

    Formatos soportados:
      - "every:Nh"  → cada N horas (cron `hour=*/N`).  N ∈ ALLOWED_INTERVAL_HOURS.
                      Las corridas se escalonan por instancia (offset en minutos
                      derivado del id) para no pegarle a todos los bancos al :00.
      - "HH:MM"     → diario a esa hora (formato legacy, pre-v0.8.32).

    Cualquier valor inválido cae al default (cada 4h).
    """
    s = (schedule_str or "").strip()

    # Offset estable por instancia: reparte los minutos para evitar que todas
    # las instancias arranquen exactamente en el mismo instante.
    minute_offset = (instance_id * 7) % 60

    if s.startswith("every:"):
        try:
            n = int(s[len("every:"):].rstrip("h"))
        except ValueError:
            n = DEFAULT_INTERVAL_HOURS
        if n not in ALLOWED_INTERVAL_HOURS:
            n = DEFAULT_INTERVAL_HOURS
        if n >= 24:
            # "1 vez al día": `*/24` no es válido (el rango de horas es 0-23),
            # así que lo expresamos como una corrida diaria a la hora 0.
            return CronTrigger(hour=0, minute=minute_offset)
        return CronTrigger(hour=f"*/{n}", minute=minute_offset)

    # Legacy "HH:MM" → diario
    try:
        hour, minute = s.split(":")
        return CronTrigger(hour=int(hour), minute=int(minute))
    except (ValueError, AttributeError):
        return CronTrigger(hour=f"*/{DEFAULT_INTERVAL_HOURS}", minute=minute_offset)


def _apply_saldo_delta(
    fuente: str,
    moneda: str,
    movimientos: list,
    log_lines: list,
    adjust_fn,
    get_saldo_fn,
) -> None:
    """
    Calcula el delta neto de los movimientos nuevos para (fuente, moneda),
    lo loguea en log_lines con detalle (saldo anterior, suma, delta, saldo nuevo)
    y lo aplica vía adjust_fn.

    Formato de la línea de log (fácil de parsear y copiar):
      Delta saldo <fuente> (<moneda>):
        saldo_anterior=$X  |  N mov. nuevos  suma_montos=$Y  delta=$Z  saldo_nuevo=$W
    """
    def _fmt(v: float) -> str:
        """Formato argentino: $1.250.000,00"""
        s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        sign = "-" if v < 0 else ("+" if v > 0 else "")
        return f"{sign}${s}"

    movs = [m for m in movimientos if m.fuente == fuente and m.moneda == moneda]
    if not movs:
        return

    suma  = round(sum(m.monto for m in movs), 2)
    delta = -round(suma, 2)
    saldo_ant = get_saldo_fn(fuente, moneda)

    if saldo_ant is not None:
        saldo_nuevo = round(saldo_ant + delta, 2)
        log_lines.append(
            f"Delta saldo {fuente} ({moneda}): "
            f"saldo_anterior={_fmt(saldo_ant)}  |  "
            f"{len(movs)} mov. nuevos  "
            f"suma_montos={_fmt(suma)}  "
            f"delta={_fmt(delta)}  "
            f"saldo_nuevo={_fmt(saldo_nuevo)}"
        )
        # Detalle por movimiento: saldo corriente después de cada uno
        # Ordenar cronológicamente para que el saldo sea rastreable
        # mov_delta = efecto sobre el saldo: egreso (monto>0) → negativo; ingreso (monto<0) → positivo
        saldo_corriente = saldo_ant
        for m in sorted(movs, key=lambda x: x.fecha):
            mov_delta = -float(m.monto)
            saldo_corriente = round(saldo_corriente + mov_delta, 2)
            desc = (m.descripcion or "")[:45]
            log_lines.append(
                f"  {m.fecha}  {desc:<45}  {_fmt(mov_delta):>16}  →  {_fmt(saldo_corriente)}"
            )
    else:
        log_lines.append(
            f"Delta saldo {fuente} ({moneda}): "
            f"saldo_anterior=N/A (auto_saldo=0 o no existe)  |  "
            f"{len(movs)} mov. nuevos  suma_montos={_fmt(suma)}  delta={_fmt(delta)}"
        )

    if delta:
        adjust_fn(fuente, delta, moneda)


def _es_pago_credito(descripcion: str, patrones: list) -> bool:
    """True si la descripción matchea algún patrón de pago/acreditación/percepción/
    ajuste — es decir, un crédito que NO es un reintegro de comercio."""
    desc = (descripcion or "").upper()
    return any(p and p.upper() in desc for p in patrones)


def _apply_tarjeta_consumo(
    fuente: str,
    movimientos: list,
    log_lines: list,
    set_fn,
    pago_patrones: list,
) -> None:
    """
    Calcula el consumo del período abierto de una tarjeta de crédito a partir del
    snapshot completo que trae el scraper (no sólo lo insertado nuevo), separado
    por moneda, y lo guarda vía set_fn.

    Los scrapers de tarjetas (galicia/bbva_tarjetas/amex) devuelven en cada run el
    período vigente completo, así que `result.movimientos` ya ES el total del
    período. La fórmula imita el total de "Cargos" que muestra el banco:
      · cargos (monto > 0)        → siempre suman
      · créditos (monto < 0):
          - si la descripción matchea `pago_patrones` (PAGO/ACREDITAC/AJUSTE/
            PERCEPCION/RG 5617) → es un pago/percepción/ajuste → se IGNORA
          - si NO matchea        → es un reintegro de comercio → se RESTA
    Así un reintegro (ej. devolución de COTO que AMEX muestra en la columna
    "Pagos" pero descuenta de los Cargos) reduce el consumo, mientras que el pago
    del resumen y las devoluciones de percepción no lo tocan.
    """
    def _consumo(moneda: str) -> float:
        total = 0.0
        for m in movimientos:
            if m.fuente != fuente or m.moneda != moneda:
                continue
            if m.monto < 0 and _es_pago_credito(m.descripcion, pago_patrones):
                continue  # pago/acreditación/percepción/ajuste → no es consumo
            total += m.monto
        return round(total, 2)

    movs = [m for m in movimientos if m.fuente == fuente]
    ars  = _consumo("ARS")
    usd  = _consumo("USD")
    set_fn(fuente, ars, usd)
    log_lines.append(
        f"Consumo tarjeta {fuente}: ARS ${ars:,.2f} · USD ${usd:,.2f} "
        f"({len(movs)} mov. del período abierto; reintegros restados, pagos ignorados)"
    )


_SCRAPER_CLASSES = {
    "amex":            "scrapers.amex:AmexScraper",
    "bbva":            "scrapers.bbva:BbvaScraper",
    "bbva_tarjetas":   "scrapers.bbva_tarjetas:BbvaTarjetasScraper",
    "galicia":         "scrapers.galicia:GaliciaScraper",
    "mercadopago":     "scrapers.mercadopago:MercadoPagoScraper",
    "invertironline":  "scrapers.invertironline:InvertirOnlineScraper",
}

# Default fuente que emite cada scraper "estándar" cuando no hay overriding por
# __cuentas__.  Usado por el remap del scheduler para scrapers single-product
# (AMEX/Galicia/MP) que tienen 1 cuenta mapeada y emiten todo a su default.
_BANCO_DEFAULT_FUENTE = {
    "amex":           "amex",
    "galicia":        "galicia_mc",
    "mercadopago":    "mercadopago",
    "invertironline": "invertironline",
    # BBVA y bbva_tarjetas NO están acá porque hacen remap per-product internamente.
}


def _remap_movimientos_to_cuentas(movimientos, cuentas: list[dict],
                                  banco: str, default_fuente: str) -> list:
    """
    Re-mapea la `fuente` de cada movimiento a la cuenta correspondiente cuando
    el scraper emitió con la fuente clásica (ej. "amex") pero la cuenta destino
    tiene una fuente custom (ej. "amex_personal").

    Para scrapers single-product (AMEX/Galicia/MP): si hay UNA cuenta mapeada,
    todos los movimientos van a ella.
    Para BBVA: ya hace remap interno via `fuente_target` por product_key, por
    eso no se llama a este helper para BBVA.
    """
    if not movimientos or not cuentas:
        return movimientos
    # Single-product: cualquier cuenta mapeada (típicamente solo una)
    target_fuente = cuentas[0].get("fuente") if cuentas else None
    if not target_fuente or target_fuente == default_fuente:
        return movimientos
    # Re-construir cada MovimientoRaw con la nueva fuente
    from scrapers.base import MovimientoRaw
    remapped = []
    for m in movimientos:
        if m.fuente == default_fuente:
            remapped.append(MovimientoRaw(
                fuente=target_fuente, fecha=m.fecha, descripcion=m.descripcion,
                monto=m.monto, moneda=m.moneda, fecha_proceso=m.fecha_proceso,
                tarjeta=m.tarjeta, raw_data=m.raw_data,
            ))
        else:
            # Scraper ya emitió con otra fuente (ej. BBVA con product_key) — respetar
            remapped.append(m)
    return remapped


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


async def _run_instance_job(instance_id: int, data_dir: str) -> None:
    """
    Job que corre una instancia específica de scraper.
    A partir de v0.4.0 — reemplaza al viejo `_run_scraper_job(banco, dir)`.

    Lee la instancia de la DB (con su config descifrada + cuentas mapeadas),
    arma el config aumentado y lo pasa al scraper.
    """
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, auto_import_unmatched
    from db import (adjust_cuenta_saldo, get_cuenta_saldo,
                    set_tarjeta_consumo, get_credit_card_fuentes)

    # Setear contexto de usuario para que DB y archivos apunten al dir correcto
    from userctx import _user_data_dir
    token = _user_data_dir.set(data_dir)

    try:
        from scraper_instances_db import (
            get_instance, get_cuentas_for_instance, update_instance_status,
        )

        inst = get_instance(instance_id)
        if not inst or not inst.get("enabled"):
            logger.info(
                "[scheduler] instancia %s (banco=%s) deshabilitada o ausente, saltando.",
                instance_id, inst.get("banco") if inst else "?",
            )
            return

        banco = inst["banco"]
        cuentas = get_cuentas_for_instance(instance_id)
        logger.info(
            "[scheduler] Iniciando instancia %d (banco=%s, nombre=%r, cuentas=%d) en %s",
            instance_id, banco, inst["nombre"], len(cuentas), data_dir,
        )

        # Augment config with __cuentas__ map para que el scraper sepa a qué
        # fuente emitir y qué productos procesar.
        config = dict(inst["config"])
        config["__cuentas__"] = cuentas
        config["__instance_id__"] = instance_id
        config["__instance_nombre__"] = inst["nombre"]

        try:
            scraper = _load_scraper(banco)
            result  = await scraper.run(config)
        except Exception as exc:
            logger.exception("[scheduler] Error ejecutando instancia %d (%s): %s",
                             instance_id, banco, exc)
            from datetime import datetime as _dt
            update_instance_status(instance_id, estado="error", error_msg=str(exc),
                                   ultimo_run=_dt.utcnow().isoformat())
            return

        if result.error:
            logger.warning("[scheduler] instancia %d (%s) terminó con error: %s",
                           instance_id, banco, result.error)
            from datetime import datetime as _dt
            update_instance_status(
                instance_id, estado="error", error_msg=result.error,
                ultimo_run=_dt.utcnow().isoformat(),
                last_log="\n".join(result.log_lines) if result.log_lines else None,
            )
            try:
                from app_log import write_scraper_run_log
                write_scraper_run_log(banco, result.log_lines)
            except Exception:
                pass
            return

        # Remap fuente para scrapers single-product (AMEX/Galicia/MP) — BBVA
        # hace remap interno via product_key.
        default_fuente = _BANCO_DEFAULT_FUENTE.get(banco)
        if default_fuente and result.movimientos:
            result.movimientos = _remap_movimientos_to_cuentas(
                result.movimientos, cuentas, banco, default_fuente,
            )

        emitted_fuentes: set[str] = set()
        inserted_dicts: list[dict] = []
        if result.movimientos:
            dicts = [m.to_dict() for m in result.movimientos]
            _dedup_log: list[str] = []
            count = insert_movimientos_raw(dicts, _out_inserted=inserted_dicts,
                                           _log_fn=_dedup_log.append)
            result.log_lines.extend(_dedup_log)
            emitted_fuentes = {d["fuente"] for d in dicts if d.get("fuente")}
            logger.info(
                "[scheduler] instancia %d (%s): %d movimientos insertados (fuentes=%s).",
                instance_id, banco, count, sorted(emitted_fuentes),
            )
        else:
            logger.info(
                "[scheduler] instancia %d (%s): sin movimientos nuevos.",
                instance_id, banco,
            )

        # Conciliar y auto-importar por CADA fuente emitida.
        for f in (emitted_fuentes or {c["fuente"] for c in cuentas} or {banco}):
            conc = run_conciliation(fuente=f)
            logger.info("[scheduler] Conciliación %s: %s", f, conc)
            imported = auto_import_unmatched(f)
            if imported:
                logger.info("[scheduler] %s: %d movimientos auto-importados a gastos.",
                            f, imported)

        # Para fuentes sin saldo de API: calcular delta neto y ajustar saldo.
        # Usar solo los movimientos efectivamente insertados en DB (inserted_dicts),
        # no result.movimientos completo, para evitar descontar movimientos que el
        # dedup de insert_movimientos_raw rechazó silenciosamente.
        from scrapers.base import MovimientoRaw as _MRaw
        inserted_movs = [
            _MRaw(fuente=d["fuente"], fecha=d["fecha"], descripcion=d["descripcion"],
                  monto=float(d["monto"]), moneda=d.get("moneda", "ARS"))
            for d in inserted_dicts
        ]
        _cc_fuentes = get_credit_card_fuentes()
        from user_config import read_user_config as _ruc
        _pago_patrones = _ruc().get(
            "tarjeta_consumo_pago_patrones",
            ["PAGO", "ACREDITAC", "AJUSTE", "PERCEPCION", "RG 5617"],
        )
        for fuente in emitted_fuentes:
            if fuente in _cc_fuentes:
                # Tarjeta: el consumo del período abierto es la suma del snapshot
                # completo del scraper (result.movimientos), no el delta nuevo.
                _apply_tarjeta_consumo(
                    fuente, result.movimientos, result.log_lines, set_tarjeta_consumo,
                    _pago_patrones,
                )
            elif fuente not in result.saldos:
                for moneda in ("ARS", "USD"):
                    _apply_saldo_delta(
                        fuente, moneda, inserted_movs,
                        result.log_lines, adjust_cuenta_saldo, get_cuenta_saldo,
                    )

        # Actualizar status de la instancia (incluye el log del delta)
        from datetime import datetime as _dt
        now_iso = _dt.utcnow().isoformat()
        _any_saldo = next(iter(result.saldos.values()), {}) if result.saldos else {}
        update_instance_status(
            instance_id,
            ultimo_run=now_iso,
            ultimo_ok=now_iso,
            estado="ok",
            error_msg=None,
            saldo_ars=_any_saldo.get("saldo_ars"),
            saldo_usd=_any_saldo.get("saldo_usd"),
            last_log="\n".join(result.log_lines) if result.log_lines else None,
        )
        # Escribir log del run al log unificado
        try:
            from app_log import write_scraper_run_log
            write_scraper_run_log(banco, result.log_lines)
        except Exception:
            pass

    finally:
        _user_data_dir.reset(token)


# Alias retro-compat: el endpoint legacy `/api/scrapers/<banco>/run-now`
# todavía existe.  Mapeamos al instance default de ese banco.
async def _run_scraper_job(banco: str, data_dir: str) -> None:
    from userctx import _user_data_dir
    token = _user_data_dir.set(data_dir)
    try:
        from scraper_instances_db import get_instance_by_banco_default
        inst = get_instance_by_banco_default(banco)
        if not inst:
            logger.info("[scheduler] no hay instancia para banco=%s, saltando.", banco)
            return
        await _run_instance_job(inst["id"], data_dir)
    finally:
        _user_data_dir.reset(token)


def start_scheduler() -> None:
    """
    Escanea cada DB de usuario (/data/*/gastos.db) y programa un job diario por
    cada `scraper_instances` enabled. No-op si no hay instancias configuradas.

    Antes de v0.4.0 leía `scraper_credentials.json` directamente.  Ahora cada
    instancia tiene su propio schedule en la tabla `scraper_instances`.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")
    jobs_added = 0

    # Iterar todos los data_dirs de usuario (donde hay gastos.db)
    data_root = os.environ.get("DATA_DIR", "/data")
    candidates: list[str] = []
    try:
        for entry in os.listdir(data_root):
            full = os.path.join(data_root, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "gastos.db")):
                candidates.append(full)
    except FileNotFoundError:
        pass
    # Fallback: /data/gastos.db directo (single-user, instalación vieja)
    if not candidates and os.path.exists(os.path.join(data_root, "gastos.db")):
        candidates.append(data_root)

    from userctx import _user_data_dir
    from scraper_instances_db import list_instances
    from db import init_db

    for data_dir in candidates:
        token = _user_data_dir.set(data_dir)
        try:
            # Asegurar que las migraciones de ESTA DB de usuario ya corrieron antes
            # de leer sus instancias.  En multi-usuario, init_db() de cada DB corre
            # lazy (en el primer request del usuario), que puede ser DESPUÉS de este
            # start_scheduler() del arranque.  Sin esto, el scheduler programaría
            # schedules sin migrar (ej. el legacy "HH:MM" diario en vez de every:4h).
            try:
                init_db()
            except Exception as exc:
                logger.warning("[scheduler] init_db() falló para %s: %s", data_dir, exc)
            instances = list_instances(enabled_only=True)
        except Exception as exc:
            logger.warning("[scheduler] No pude listar instancias de %s: %s",
                           data_dir, exc)
            instances = []
        finally:
            _user_data_dir.reset(token)

        for inst in instances:
            schedule_str = inst.get("schedule") or DEFAULT_SCHEDULE
            trigger = parse_schedule(schedule_str, inst["id"])

            job_id = f"scraper_inst_{inst['id']}_{os.path.basename(data_dir)}"
            _scheduler.add_job(
                _run_instance_job,
                trigger=trigger,
                args=[inst["id"], data_dir],
                id=job_id,
                name=f"{inst['banco']} ({inst['nombre']})",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            jobs_added += 1
            logger.info(
                "[scheduler] Programado inst %d (%s/%s) schedule=%r en %s",
                inst["id"], inst["banco"], inst["nombre"],
                schedule_str, os.path.basename(data_dir),
            )

    # Notifier de vencimientos (feature b1): job horario, independiente de los
    # scrapers. Corre cada hora a :05; cada usuario decide su hora vía config y la
    # dedup evita repetir. Se agrega SIEMPRE (aunque no haya scrapers).
    try:
        from vencimiento_notifier import run_for_all_users
        _scheduler.add_job(
            run_for_all_users,
            trigger=CronTrigger(minute=5),
            id="venc_notifier",
            name="Notifier de vencimientos",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("[scheduler] Notifier de vencimientos programado (horario, :05).")
    except Exception as exc:
        logger.warning("[scheduler] No pude programar el notifier de vencimientos: %s", exc)

    if jobs_added == 0:
        logger.info(
            "[scheduler] Sin instancias de scraper configuradas — sólo corre el "
            "notifier de vencimientos. Configurá scrapers en Config → Scrapers."
        )

    _scheduler.start()
    logger.info("[scheduler] Iniciado con %d jobs de scraper + notifier de vencimientos.", jobs_added)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reload_scheduler() -> None:
    """
    Recarga los jobs del scheduler.  Safe to call from any context — si no hay
    event loop corriendo (típico cuando un endpoint sync hace reload), se loguea
    un warning y se saltea (los cambios se aplican en el próximo arranque del
    add-on o en un reload async posterior).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "[scheduler] reload_scheduler() llamado desde contexto sin event "
            "loop — skipping.  Los cambios se aplican en el próximo restart "
            "del add-on (o llamá POST /api/scrapers/scheduler/reload desde un "
            "endpoint async)."
        )
        return
    stop_scheduler()
    start_scheduler()


async def run_scraper_now(banco: str, data_dir: str | None = None) -> dict:
    """
    Trigger manual de un scraper, identificado por el banco-key (legacy API).
    Mapea a la primera instancia (default) de ese banco.
    Para correr una instancia específica usar `run_instance_now(instance_id, ...)`.
    """
    from userctx import _user_data_dir, get_data_dir
    effective_dir = data_dir or get_data_dir()
    token = _user_data_dir.set(effective_dir)
    try:
        from scraper_instances_db import get_instance_by_banco_default
        inst = get_instance_by_banco_default(banco)
        if not inst:
            return {"ok": False, "error":
                    f"'{banco}' no tiene instancia configurada. "
                    f"Creá una desde Config → Scrapers."}
        # delega al runner por-instancia
        return await run_instance_now(inst["id"], effective_dir)
    finally:
        _user_data_dir.reset(token)


async def run_instance_now(instance_id: int, data_dir: str | None = None) -> dict:
    """
    Trigger manual de UNA instancia específica.  Devuelve el resultado agregado.
    """
    from conciliacion import run_conciliation
    from scrapers_db import insert_movimientos_raw, auto_import_unmatched
    from scraper_instances_db import (
        get_instance, get_cuentas_for_instance, update_instance_status,
    )
    from userctx import _user_data_dir, get_data_dir
    from db import (adjust_cuenta_saldo, get_cuenta_saldo,
                    set_tarjeta_consumo, get_credit_card_fuentes)

    effective_dir = data_dir or get_data_dir()
    token = _user_data_dir.set(effective_dir)
    try:
        inst = get_instance(instance_id)
        if not inst:
            return {"ok": False, "error": f"Instancia {instance_id} no encontrada."}

        banco = inst["banco"]
        cuentas = get_cuentas_for_instance(instance_id)

        config = dict(inst["config"])
        config["__cuentas__"] = cuentas
        config["__instance_id__"] = instance_id
        config["__instance_nombre__"] = inst["nombre"]

        try:
            scraper = _load_scraper(banco)
            result  = await scraper.run(config)
        except Exception as exc:
            msg = f"Error al ejecutar scraper: {exc}"
            logger.exception(msg)
            from datetime import datetime as _dt
            update_instance_status(instance_id, estado="error", error_msg=str(exc),
                                   ultimo_run=_dt.utcnow().isoformat())
            return {"ok": False, "error": msg}

        if result.error:
            from datetime import datetime as _dt
            update_instance_status(
                instance_id, estado="error", error_msg=result.error,
                ultimo_run=_dt.utcnow().isoformat(),
                last_log="\n".join(result.log_lines) if result.log_lines else None,
            )
            try:
                from app_log import write_scraper_run_log
                write_scraper_run_log(banco, result.log_lines)
            except Exception:
                pass
            return {"ok": False, "error": result.error,
                    "session_expired": result.session_expired}

        # Remap fuente para single-product scrapers (mismo helper que _run_instance_job)
        default_fuente = _BANCO_DEFAULT_FUENTE.get(banco)
        if default_fuente and result.movimientos:
            result.movimientos = _remap_movimientos_to_cuentas(
                result.movimientos, cuentas, banco, default_fuente,
            )

        inserted = 0
        emitted_fuentes: set[str] = set()
        inserted_dicts: list[dict] = []
        if result.movimientos:
            dicts    = [m.to_dict() for m in result.movimientos]
            _dedup_log: list[str] = []
            inserted = insert_movimientos_raw(dicts, _out_inserted=inserted_dicts,
                                              _log_fn=_dedup_log.append)
            result.log_lines.extend(_dedup_log)
            emitted_fuentes = {d["fuente"] for d in dicts if d.get("fuente")}

        conc_agg = {"matched": 0, "unmatched": 0, "errors": 0}
        auto_imported = 0
        for f in (emitted_fuentes or {c["fuente"] for c in cuentas} or {banco}):
            c = run_conciliation(fuente=f)
            for k in ("matched", "unmatched", "errors"):
                conc_agg[k] += c.get(k, 0)
            auto_imported += auto_import_unmatched(f)

        # Para fuentes sin saldo de API: calcular delta solo sobre movimientos
        # efectivamente insertados (no todos los detectados por el scraper).
        from scrapers.base import MovimientoRaw as _MRaw
        inserted_movs = [
            _MRaw(fuente=d["fuente"], fecha=d["fecha"], descripcion=d["descripcion"],
                  monto=float(d["monto"]), moneda=d.get("moneda", "ARS"))
            for d in inserted_dicts
        ]
        _cc_fuentes = get_credit_card_fuentes()
        from user_config import read_user_config as _ruc
        _pago_patrones = _ruc().get(
            "tarjeta_consumo_pago_patrones",
            ["PAGO", "ACREDITAC", "AJUSTE", "PERCEPCION", "RG 5617"],
        )
        for fuente in emitted_fuentes:
            if fuente in _cc_fuentes:
                _apply_tarjeta_consumo(
                    fuente, result.movimientos, result.log_lines, set_tarjeta_consumo,
                    _pago_patrones,
                )
            elif fuente not in result.saldos:
                for moneda in ("ARS", "USD"):
                    _apply_saldo_delta(
                        fuente, moneda, inserted_movs,
                        result.log_lines, adjust_cuenta_saldo, get_cuenta_saldo,
                    )

        # Actualizar status (incluye el log del delta de saldo)
        from datetime import datetime as _dt
        now_iso = _dt.utcnow().isoformat()
        _any_saldo = next(iter(result.saldos.values()), {}) if result.saldos else {}
        update_instance_status(
            instance_id,
            ultimo_run=now_iso,
            ultimo_ok=now_iso,
            estado="ok",
            error_msg=None,
            saldo_ars=_any_saldo.get("saldo_ars"),
            saldo_usd=_any_saldo.get("saldo_usd"),
            movimientos_nuevos=inserted,
            last_log="\n".join(result.log_lines) if result.log_lines else None,
        )
        # Escribir log del run al log unificado
        try:
            from app_log import write_scraper_run_log
            write_scraper_run_log(banco, result.log_lines)
        except Exception:
            pass

        return {
            "ok":            True,
            "banco":         banco,
            "instance_id":   instance_id,
            "movimientos":   inserted,
            "auto_imported": auto_imported,
            "conciliacion":  conc_agg,
            "saldos":        result.saldos,
            "timestamp":     now_iso,
        }
    finally:
        _user_data_dir.reset(token)


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

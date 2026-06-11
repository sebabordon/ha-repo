"""
Notifier de vencimientos de tarjeta (feature b1).

Manda un Web Push N días antes de cada vencimiento de tarjeta IMPAGO. Reusa:
  - `list_vencimientos()` (db.py): ya calcula, por fuente, el último resumen con
    fecha_venc y si está pagado (pago_confirmado / pago_probable).
  - `send_push()` (routes/push.py): la feature "a".

Config per-usuario (user_config): venc_notif_activo (opt-in), venc_notif_dias_antes
(umbrales de antelación) y venc_notif_hora (hora local ART). La dedup vive en la
tabla venc_notificaciones (clave = fuente|fecha_venc|umbral) → no repite el mismo
aviso. Corre como job HORARIO del scheduler; cada usuario sólo recibe a su hora.
"""
import logging
import os
from datetime import datetime, timezone, timedelta, date

logger = logging.getLogger(__name__)

# Argentina es UTC-3 todo el año (sin DST desde 2009) → offset fijo, sin depender
# de que la imagen tenga tzdata instalado.
_ART = timezone(timedelta(hours=-3))

_FUENTE_LABELS = {
    "amex":       "AMEX",
    "bbva_mc":    "BBVA Mastercard",
    "bbva_visa":  "BBVA Visa",
    "galicia_mc": "Galicia Mastercard",
}


def _fuente_label(fuente: str) -> str:
    return _FUENTE_LABELS.get(fuente, (fuente or "Tarjeta").replace("_", " ").title())


def _fmt_monto(monto) -> str:
    try:
        return "$ " + f"{float(monto):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


def notify_current_user(force: bool = False) -> int:
    """
    Corre EN CONTEXTO de un usuario (userctx ya seteado). Devuelve cuántos push
    mandó. No levanta excepción hacia afuera salvo bugs de programación.

    force=True (botón "Probar aviso ahora"): ignora el opt-in, la hora y la dedup
    — manda igual y NO marca como enviado, para no suprimir el aviso real.
    """
    from user_config import read_user_config
    cfg = read_user_config()
    if not force and not cfg.get("venc_notif_activo"):
        return 0

    now_art = datetime.now(timezone.utc).astimezone(_ART)
    try:
        hora = int(cfg.get("venc_notif_hora", 9))
    except (TypeError, ValueError):
        hora = 9
    if not force and now_art.hour != hora:
        return 0  # sólo a la hora elegida por el usuario (job corre cada hora)

    thresholds = set()
    for x in (cfg.get("venc_notif_dias_antes") or [3, 1]):
        try:
            thresholds.add(int(x))
        except (TypeError, ValueError):
            pass
    if not thresholds:
        return 0

    from routes.push import list_subscriptions, send_push
    subs = list_subscriptions()
    if not subs:
        return 0  # sin dispositivos suscriptos, nada que mandar

    from db import list_vencimientos, venc_notif_already_sent, venc_notif_mark_sent, _conn

    # Último resumen por fuente (mayor fecha_venc).
    latest: dict[str, dict] = {}
    for v in list_vencimientos():
        f, fv = v.get("fuente"), v.get("fecha_venc")
        if not f or not fv:
            continue
        if f not in latest or fv > latest[f].get("fecha_venc", ""):
            latest[f] = v

    today = now_art.date()
    sent = 0
    dead_all: list[str] = []

    for f, v in latest.items():
        if v.get("pago_confirmado") or v.get("pago_probable"):
            continue  # ya pagada
        try:
            due = date.fromisoformat(str(v["fecha_venc"])[:10])
        except (TypeError, ValueError):
            continue
        days = (due - today).days
        if days not in thresholds:
            continue
        clave = f"{f}|{v['fecha_venc']}|{days}"
        if not force and venc_notif_already_sent(clave):
            continue

        label = _fuente_label(f)
        if days <= 0:
            title = f"💳 {label} vence hoy"
        elif days == 1:
            title = f"💳 {label} vence mañana"
        else:
            title = f"💳 {label} vence en {days} días"
        monto = v.get("total_ars") or v.get("sum_ars") or 0
        body = (f"Saldo a pagar ~ {_fmt_monto(monto)}".strip()
                if monto else "Vencimiento impago")

        ok, dead = send_push(subs, title, body, "/")
        dead_all.extend(dead)
        if ok:
            if not force:
                venc_notif_mark_sent(clave)
            sent += 1
            logger.info("[venc-notif] %s: push enviado (faltan %d días, %d subs)%s",
                        label, days, ok, " [test]" if force else "")

    # Limpiar suscripciones muertas detectadas durante el envío.
    if dead_all:
        with _conn() as conn:
            for ep in dead_all:
                conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (ep,))

    return sent


def run_for_all_users() -> None:
    """
    Job del scheduler (horario). Itera /data/*/ y notifica a cada usuario en su
    propio contexto. Función sync → APScheduler la corre en un thread del executor.
    """
    data_root = os.environ.get("DATA_DIR", "/data")
    from userctx import _user_data_dir

    candidates: list[str] = []
    try:
        for entry in os.listdir(data_root):
            full = os.path.join(data_root, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "gastos.db")):
                candidates.append(full)
    except FileNotFoundError:
        return

    for data_dir in candidates:
        token = _user_data_dir.set(data_dir)
        try:
            notify_current_user()
        except Exception as exc:
            logger.warning("[venc-notif] error procesando %s: %s", data_dir, exc)
        finally:
            _user_data_dir.reset(token)

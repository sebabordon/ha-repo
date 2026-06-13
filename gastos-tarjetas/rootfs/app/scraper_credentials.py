"""
Gestión de credenciales de scrapers — por usuario.

A partir de v0.6.16 las credenciales viven SOLO en la tabla `scraper_instances`
de la DB del usuario (cifradas con Fernet si SCRAPER_ENCRYPTION_KEY está
configurada).  El archivo scraper_credentials.json que existía en versiones
anteriores ya no se escribe; los archivos viejos que queden en disco son
inofensivos y pueden borrarse manualmente.

El módulo conserva `BANKS` (metadatos de la UI: campos, labels) y las
funciones públicas con la misma firma para que el resto del código no cambie.
"""

import logging
import os
from contextlib import contextmanager

from userctx import _user_data_dir, get_data_dir

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", "/data")

# ── Definición de bancos ──────────────────────────────────────────────────────
# Solo metadatos de UI: nombre visible, campos del formulario, schedule default.
# Los valores reales (credenciales, enabled, schedule) están en scraper_instances.

BANKS: dict[str, dict] = {
    "amex": {
        "nombre":   "AMEX Argentina",
        "schedule": "every:4h",
        "campos": [
            {"key": "usuario",  "label": "Usuario (email)",  "type": "text",     "required": True},
            {"key": "password", "label": "Contraseña",       "type": "password", "required": True},
            {
                "key":      "auto_resumenes",
                "label":    "Descargar resúmenes PDF automáticamente",
                "type":     "checkbox",
                "required": False,
                "hint":     "Si está activo, en cada run el scraper navega a la sección Resúmenes de AMEX, descarga el PDF más reciente y lo importa directo a Gastos (equivalente a subirlo manualmente).",
            },
            {
                "key":      "statements_account_key",
                "label":    "Account Key (Resúmenes PDF)",
                "type":     "text",
                "required": False,
                "hint":     "Filtra la página de Resúmenes para mostrar solo los de la tarjeta principal. Sin este campo el portal muestra los resúmenes de la tarjeta adicional. Obtenerlo: en el HAR del portal de AMEX buscar la petición a /statements y copiar el parámetro account_key de la URL (ej. 00B5C8FF8254B6D66D600ACC4A35D20E).",
            },
            {
                "key":         "resumenes_meses",
                "label":       "Meses de resúmenes a importar",
                "type":        "text",
                "required":    False,
                "placeholder": "1",
                "hint":        "Cuántos meses hacia atrás bajar resúmenes PDF cuando 'Descargar resúmenes' está activo. 1 = solo el último (default). 3 = los de los últimos 3 meses. Los ya importados se saltean. Útil para backfill.",
            },
        ],
    },
    "bbva": {
        "nombre":   "BBVA Argentina",
        "schedule": "every:4h",
        "campos": [
            {"key": "usuario",     "label": "Número de DNI",       "type": "text",     "required": True,
             "hint": "Solo el número, sin puntos (ej. 12345678)"},
            {"key": "tercer_dato", "label": "Usuario BBVA",        "type": "text",     "required": True,
             "hint": "El nombre de usuario que configuraste en homebanking (no el DNI)"},
            {"key": "password",    "label": "Contraseña",          "type": "password", "required": True},
            {
                "key":         "dias",
                "label":       "Días a consultar",
                "type":        "text",
                "required":    False,
                "placeholder": "60",
                "hint":        "1 = solo hoy, 2 = hoy y ayer, N = últimos N días (default: 60)",
            },
            {
                "key":         "usuario_default",
                "label":       "Usuario para los gastos importados",
                "type":        "text",
                "required":    False,
                "placeholder": "Titular",
                "hint":        "Nombre que verán los gastos importados de este scraper (ej. Titular, Sebastián). Si está vacío, se usa el default configurado en Config → Usuarios → fuente_usuario['bbva_cuenta'].",
            },
            {
                "key":         "monedas",
                "label":       "Monedas a importar (legacy)",
                "type":        "text",
                "required":    False,
                "placeholder": "ARS",
                "hint":        "Códigos de moneda separados por coma (ej. ARS, USD, EUR). Vacío = solo ARS. Filtra qué cuentas BBVA procesar. NOTA: en v0.4.0+ este campo se usa SOLO si la instancia no tiene cuentas mapeadas (modo legacy). Cuando linkees cuentas desde la tab Cuentas, este campo se ignora porque las cuentas ya implican qué monedas procesar.",
            },
            {
                "key":      "filtro_fecha_api",
                "label":    "Filtrar fechas en la API",
                "type":     "checkbox",
                "required": False,
                "default":  True,
                "hint":     "Activado (default): BBVA filtra los movimientos server-side, más eficiente pero devuelve saldo=0 por movimiento. Desactivado: fechas vacías en el request, BBVA devuelve el saldo corriente real por movimiento (útil para dedup preciso), el filtrado por rango se hace client-side.",
            },
            {
                "key":      "auto_resumenes",
                "label":    "Descargar resúmenes PDF automáticamente",
                "type":     "checkbox",
                "required": False,
                "hint":     "Si está activo, en cada run el scraper descarga el resumen PDF más reciente de la Caja de Ahorro Pesos y lo importa directo a Gastos (equivalente a subirlo manualmente).",
            },
            {
                "key":         "resumenes_meses",
                "label":       "Meses de resúmenes a importar",
                "type":        "text",
                "required":    False,
                "placeholder": "1",
                "hint":        "Cuántos meses hacia atrás bajar resúmenes PDF cuando 'Descargar resúmenes' está activo. 1 = solo el último (default). 3 = los de los últimos 3 meses. Los ya importados se saltean. Útil para backfill tras un reset de la cuenta.",
            },
        ],
    },
    "bbva_tarjetas": {
        "nombre":   "BBVA Argentina — Tarjetas de Crédito",
        "schedule": "every:4h",
        "campos": [
            {"key": "usuario",     "label": "Número de DNI",       "type": "text",     "required": True,
             "hint": "Solo el número, sin puntos (ej. 12345678)"},
            {"key": "tercer_dato", "label": "Usuario BBVA",        "type": "text",     "required": True,
             "hint": "El nombre de usuario que configuraste en homebanking (no el DNI)"},
            {"key": "password",    "label": "Contraseña",          "type": "password", "required": True},
            {
                "key":         "usuario_default",
                "label":       "Usuario para los gastos importados",
                "type":        "text",
                "required":    False,
                "placeholder": "Titular",
                "hint":        "Nombre que verán los gastos importados (ej. Titular, Sebastián).",
            },
            {
                "key":      "auto_resumenes",
                "label":    "Descargar resúmenes PDF automáticamente",
                "type":     "checkbox",
                "required": False,
                "hint":     "Si está activo, en cada run el scraper descarga el resumen PDF más reciente de VISA y Mastercard y lo importa directo a Gastos (equivalente a subirlo manualmente).",
            },
            {
                "key":         "resumenes_meses",
                "label":       "Meses de resúmenes a importar",
                "type":        "text",
                "required":    False,
                "placeholder": "1",
                "hint":        "Cuántos meses hacia atrás bajar resúmenes PDF de VISA/Mastercard cuando 'Descargar resúmenes' está activo. 1 = solo el último (default). 3 = los de los últimos 3 meses. Los ya importados se saltean.",
            },
        ],
    },
    "galicia": {
        "nombre":   "Banco Galicia",
        "schedule": "every:4h",
        "campos": [
            {"key": "usuario",     "label": "Número de DNI",       "type": "text",     "required": True,
             "hint": "Solo el número, sin puntos (ej. 12345678)"},
            {"key": "tercer_dato", "label": "Usuario homebanking",  "type": "text",     "required": True,
             "hint": "El alias/usuario que configuraste en Galicia Online Banking (no el DNI)"},
            {"key": "password",    "label": "Contraseña",           "type": "password", "required": True},
        ],
        "totp": True,
    },
    "invertironline": {
        "nombre":   "InvertirOnline",
        "schedule": "every:4h",
        "campos": [
            {"key": "usuario",  "label": "Usuario",    "type": "text",     "required": True,
             "hint": "Tu usuario de IOL (generalmente tu email)"},
            {"key": "password", "label": "Contraseña", "type": "password", "required": True},
            {
                "key":         "dias",
                "label":       "Días a consultar (operaciones)",
                "type":        "text",
                "required":    False,
                "placeholder": "60",
                "hint":        "Días hacia atrás para importar compras/ventas. Solo aplica con 'Importar operaciones' activo.",
            },
            {
                "key":      "importar_operaciones",
                "label":    "Importar operaciones (compras/ventas)",
                "type":     "checkbox",
                "required": False,
                "hint":     "Si está activo, importa compras y ventas como movimientos en la pestaña Gastos.",
            },
        ],
    },
    "mercadopago": {
        "nombre":   "MercadoPago",
        "schedule": "every:4h",
        "campos": [
            {
                "key":      "access_token",
                "label":    "Access Token",
                "type":     "password",
                "required": True,
                "hint":     "Generalo en mercadopago.com.ar/developers/panel → tu app → Credenciales de producción",
            },
            {
                "key":         "usuario",
                "label":       "Usuario (nombre)",
                "type":        "text",
                "required":    False,
                "placeholder": "Titular",
                "hint":        "Nombre del titular para etiquetar los gastos importados (ej. Titular, Juan)",
            },
            {
                "key":         "dias",
                "label":       "Días a consultar",
                "type":        "text",
                "required":    False,
                "placeholder": "60",
                "hint":        "1 = solo hoy, 2 = hoy y ayer, N = últimos N días (default: 60)",
            },
            {
                "key":         "debug_log",
                "label":       "Log de debug",
                "type":        "checkbox",
                "required":    False,
                "hint":        "Registra cada pago procesado (id, tipo, operación, monto). Visible en Supervisión → Add-ons → Gastos → Log.",
            },
        ],
    },
}

# Campos que nunca se devuelven en las respuestas de la API
_SECRET_FIELDS = frozenset(
    f["key"]
    for bank in BANKS.values()
    for f in bank["campos"]
    if f["type"] == "password"
)

# Links cuenta-default por banco (para crear instancias al configurar por primera vez)
_DEFAULT_LINK: dict[str, tuple[str, str]] = {
    "bbva":           ("bbva_cuenta",    "ARS"),
    "bbva_tarjetas":  ("bbva_visa",      "VISA"),
    "amex":           ("amex",           "main"),
    "galicia":        ("galicia_mc",     "main"),
    "mercadopago":    ("mercadopago",    "main"),
    "invertironline": ("invertironline", "main"),
}


# ── Helper de contexto ────────────────────────────────────────────────────────

@contextmanager
def _with_data_dir(data_dir: str | None):
    """Setea temporalmente el data_dir del usuario si se provee explícitamente."""
    if data_dir is not None:
        token = _user_data_dir.set(data_dir)
        try:
            yield
        finally:
            _user_data_dir.reset(token)
    else:
        yield


# ── API pública ───────────────────────────────────────────────────────────────

def get_bank_config(banco: str, data_dir: str | None = None) -> dict | None:
    """
    Devuelve la config de un banco si está habilitado, o None.
    Lee de scraper_instances (la instancia default del banco).
    """
    from scraper_instances_db import get_instance_by_banco_default
    with _with_data_dir(data_dir):
        inst = get_instance_by_banco_default(banco)
    if not inst or not inst.get("enabled"):
        return None
    cfg = dict(inst["config"])
    if "schedule" not in cfg:
        cfg["schedule"] = inst.get("schedule") or (
            BANKS[banco]["schedule"] if banco in BANKS else "07:00"
        )
    return cfg


def set_bank_config(banco: str, updates: dict, data_dir: str | None = None) -> None:
    """
    Guarda/actualiza la config de un banco en scraper_instances.

    Reglas especiales para contraseñas:
      - Campo vacío ("") → mantener el valor existente.
      - Campo con valor → sobrescribir.
    """
    from scraper_instances_db import (
        get_instance_by_banco_default, update_instance, create_instance, link_cuenta,
    )

    with _with_data_dir(data_dir):
        inst = get_instance_by_banco_default(banco)

    if inst:
        merged = dict(inst["config"])
        for k, v in updates.items():
            if k in _SECRET_FIELDS and not v:
                pass  # preservar contraseña existente
            else:
                merged[k] = v
        with _with_data_dir(data_dir):
            update_instance(
                inst["id"],
                config=merged,
                schedule=merged.get("schedule"),
                enabled=bool(merged.get("enabled")),
            )
    else:
        label = banco.upper() if banco != "mercadopago" else "MercadoPago"
        with _with_data_dir(data_dir):
            new_id = create_instance(
                banco=banco, nombre=f"{label} default",
                config=updates,
                schedule=updates.get("schedule"),
                enabled=bool(updates.get("enabled")),
            )
            link = _DEFAULT_LINK.get(banco)
            if link:
                cuenta_fuente, product_key = link
                try:
                    link_cuenta(cuenta_fuente, new_id, product_key)
                except Exception as exc:
                    logger.warning("No se pudo linkear cuenta %s: %s", cuenta_fuente, exc)


def creds_for_api(data_dir: str | None = None) -> dict:
    """
    Devuelve la config de todos los bancos apta para el browser:
      - Campos password reemplazados por "" con has_<field>=True/False.
      - Metadatos de cada banco (nombre, campos, totp).
    Lee de scraper_instances (la instancia default por banco).
    """
    from scraper_instances_db import list_instances
    with _with_data_dir(data_dir):
        instances = list_instances()

    # Una entrada por banco: la primera instancia (default)
    by_banco: dict[str, dict] = {}
    for inst in instances:
        if inst["banco"] not in by_banco:
            by_banco[inst["banco"]] = inst

    result = {}
    for banco, bank_def in BANKS.items():
        inst = by_banco.get(banco)
        cfg  = inst["config"] if inst else {}

        row: dict = {
            "enabled":  bool(inst["enabled"]) if inst else False,
            "schedule": inst["schedule"] if inst else bank_def["schedule"],
            "nombre":   bank_def["nombre"],
            "totp":     bank_def.get("totp", False),
            "campos":   bank_def["campos"],
        }
        for campo in bank_def["campos"]:
            key = campo["key"]
            if campo["type"] == "password":
                row[key]          = ""
                row[f"has_{key}"] = bool(cfg.get(key))
            elif campo["type"] == "checkbox":
                row[key] = bool(cfg.get(key, False))
            else:
                row[key] = cfg.get(key, "")

        result[banco] = row

    return result


def find_all_enabled_configs() -> list[dict]:
    """
    Devuelve todos los scrapers habilitados en todos los directorios de usuario.
    Lee de scraper_instances en cada gastos.db encontrado bajo DATA_DIR.
    """
    from scraper_instances_db import list_instances

    results  = []
    candidates: list[str] = []
    try:
        for entry in os.listdir(_DATA_DIR):
            full = os.path.join(_DATA_DIR, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "gastos.db")):
                candidates.append(full)
    except FileNotFoundError:
        pass
    # Fallback: instalación single-user (gastos.db directo en /data)
    if not candidates and os.path.exists(os.path.join(_DATA_DIR, "gastos.db")):
        candidates.append(_DATA_DIR)

    for data_dir in candidates:
        token = _user_data_dir.set(data_dir)
        try:
            instances = list_instances(enabled_only=True)
        except Exception as exc:
            logger.warning("Error leyendo instancias de %s: %s", data_dir, exc)
            instances = []
        finally:
            _user_data_dir.reset(token)

        for inst in instances:
            banco = inst["banco"]
            if banco not in BANKS:
                continue
            cfg = dict(inst["config"])
            if "schedule" not in cfg:
                cfg["schedule"] = inst.get("schedule") or BANKS[banco]["schedule"]
            results.append({
                "banco":    banco,
                "data_dir": data_dir,
                "config":   cfg,
            })

    return results

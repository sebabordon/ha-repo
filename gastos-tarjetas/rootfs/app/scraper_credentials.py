"""
Gestión de credenciales de scrapers — por usuario.

Las credenciales se guardan en {data_dir}/scraper_credentials.json, donde
data_dir es el directorio del usuario autenticado (/data/{email_sanitizado}/).

Esto significa que cada usuario que configure sus propios scrapers tiene sus
credenciales separadas y ligadas a su instancia de gastos.db.

El scheduler lee todos los archivos scraper_credentials.json encontrados bajo
/data/*/  para poder ejecutar jobs sin contexto de request HTTP.

Formato del JSON:
    {
      "amex": {
        "enabled": true,
        "usuario": "user@mail.com",
        "password": "...",
        "schedule": "07:00"
      },
      "bbva": {
        "enabled": false,
        "usuario": "12345678",
        "tercer_dato": "mi_usuario_bbva",
        "password": "...",
        "dias": "60",
        "schedule": "07:15"
      },
      ...
    }

Las contraseñas se cifran si SCRAPER_ENCRYPTION_KEY está configurada en el add-on
(Fernet/AES-128 vía scraper_crypto.py).  Sin esa clave se almacenan en texto claro
como fallback para no romper instalaciones sin la variable.
"""

import glob
import json
import logging
import os

from scraper_crypto import decrypt_str, encrypt_str
from userctx import get_data_dir

logger = logging.getLogger(__name__)

_FILENAME = "scraper_credentials.json"
_DATA_DIR = os.environ.get("DATA_DIR", "/data")

# ── Definición de bancos ──────────────────────────────────────────────────────
# Cada banco tiene nombre visible, campos de credenciales y schedule por defecto.
# Los campos con type="password" nunca se devuelven en las respuestas GET.

BANKS: dict[str, dict] = {
    "amex": {
        "nombre":   "AMEX Argentina",
        "schedule": "07:00",
        "campos": [
            {"key": "usuario",  "label": "Usuario (email)",  "type": "text",     "required": True},
            {"key": "password", "label": "Contraseña",       "type": "password", "required": True},
        ],
    },
    "bbva": {
        "nombre":   "BBVA Argentina",
        "schedule": "07:15",
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
        ],
    },
    "bbva_tarjetas": {
        "nombre":   "BBVA Argentina — Tarjetas de Crédito",
        "schedule": "07:20",
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
        ],
    },
    "galicia": {
        "nombre":   "Banco Galicia",
        "schedule": "07:30",
        "campos": [
            {"key": "usuario",     "label": "Número de DNI",       "type": "text",     "required": True,
             "hint": "Solo el número, sin puntos (ej. 12345678)"},
            {"key": "tercer_dato", "label": "Usuario homebanking",  "type": "text",     "required": True,
             "hint": "El alias/usuario que configuraste en Galicia Online Banking (no el DNI)"},
            {"key": "password",    "label": "Contraseña",           "type": "password", "required": True},
        ],
        "totp": True,   # puede pedir código de verificación en el primer login
    },
    "invertironline": {
        "nombre":   "InvertirOnline",
        "schedule": "08:00",
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
        "schedule": "07:45",
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


# ── Rutas ─────────────────────────────────────────────────────────────────────

def _creds_path(data_dir: str | None = None) -> str:
    return os.path.join(data_dir or get_data_dir(), _FILENAME)


# ── Lectura / escritura ───────────────────────────────────────────────────────

def read_creds(data_dir: str | None = None) -> dict:
    """Lee el JSON de credenciales del usuario. Devuelve {} si no existe.

    Soporta el formato cifrado ({"_encrypted": true, "_data": "<token>"})
    generado por write_creds cuando SCRAPER_ENCRYPTION_KEY está configurada.
    Los archivos en formato plaintext (instalaciones anteriores) se leen tal cual.
    """
    path = _creds_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            raw = json.load(f) or {}
        if raw.get("_encrypted"):
            plaintext = decrypt_str(raw.get("_data", ""), True)
            return json.loads(plaintext) if plaintext else {}
        return raw
    except Exception as exc:
        logger.error("Error leyendo scraper_credentials.json: %s", exc)
        return {}


def write_creds(data: dict, data_dir: str | None = None) -> None:
    """Escribe el JSON de credenciales del usuario.

    Si SCRAPER_ENCRYPTION_KEY está disponible, cifra el contenido completo
    con Fernet antes de escribir en disco.  De lo contrario escribe plaintext
    (comportamiento original).
    """
    path = _creds_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plaintext = json.dumps(data, ensure_ascii=False)
    encrypted_data, is_enc = encrypt_str(plaintext)
    to_save = {"_encrypted": True, "_data": encrypted_data} if is_enc else data
    with open(path, "w") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    logger.info("scraper_credentials.json guardado en %s", os.path.dirname(path))


def get_bank_config(banco: str, data_dir: str | None = None) -> dict | None:
    """
    Devuelve la config de un banco si está habilitado, o None.
    Usado por el scheduler y los endpoints HTTP para obtener credenciales reales.
    """
    creds = read_creds(data_dir)
    cfg   = creds.get(banco, {})
    if not cfg.get("enabled", False):
        return None
    # Asegurar que el schedule tenga un valor
    if "schedule" not in cfg:
        cfg = dict(cfg)
        cfg["schedule"] = BANKS[banco]["schedule"] if banco in BANKS else "07:00"
    return cfg


def set_bank_config(banco: str, updates: dict, data_dir: str | None = None) -> None:
    """
    Actualiza la config de un banco.

    Reglas especiales para las contraseñas:
      - Si el campo viene vacío ("") → mantener el valor existente
      - Si viene con valor → sobrescribir
    """
    creds   = read_creds(data_dir)
    existing = creds.get(banco, {})

    # Preservar contraseñas existentes si el campo llega vacío
    merged = dict(existing)
    for k, v in updates.items():
        if k in _SECRET_FIELDS and not v:
            # Mantener el valor previo
            pass
        else:
            merged[k] = v

    creds[banco] = merged
    write_creds(creds, data_dir)

    # Mirror a la instancia default del banco en `scraper_instances` (v0.4.0+).
    # Si la instancia no existe, la creamos (caso: usuario habilitó un banco
    # nuevo después de la migración inicial).
    try:
        from scraper_instances_db import (
            get_instance_by_banco_default, update_instance, create_instance, link_cuenta,
        )
        inst = get_instance_by_banco_default(banco)
        if inst:
            update_instance(
                inst["id"],
                config=merged,
                schedule=merged.get("schedule"),
                enabled=bool(merged.get("enabled")),
            )
        else:
            # Crear instancia + linkear cuenta default del banco
            _DEFAULT_LINK = {
                "bbva":           ("bbva_cuenta",    "ARS"),
                "bbva_tarjetas":  ("bbva_visa",      "VISA"),
                "amex":           ("amex",           "main"),
                "galicia":        ("galicia_mc",     "main"),
                "mercadopago":    ("mercadopago",    "main"),
                "invertironline": ("invertironline", "main"),
            }
            link = _DEFAULT_LINK.get(banco)
            label = banco.upper() if banco != "mercadopago" else "MercadoPago"
            new_id = create_instance(
                banco=banco, nombre=f"{label} default",
                config=merged, schedule=merged.get("schedule"),
                enabled=bool(merged.get("enabled")),
            )
            if link:
                cuenta_fuente, product_key = link
                link_cuenta(cuenta_fuente, new_id, product_key)
    except Exception as exc:
        logger.warning("Mirror a scraper_instances falló: %s", exc)


# ── Respuesta para la API (sin contraseñas) ────────────────────────────────────

def creds_for_api(data_dir: str | None = None) -> dict:
    """
    Devuelve la config de todos los bancos apta para enviar al browser:
      - Los campos de tipo 'password' se reemplazan por ""
      - Se agrega 'has_password': True/False para que la UI sepa si ya hay una
      - Se incluyen los metadatos de cada banco (nombre, campos, totp)
    """
    creds = read_creds(data_dir)
    result = {}

    for banco, bank_def in BANKS.items():
        stored = creds.get(banco, {})
        row: dict = {
            "enabled":  stored.get("enabled", False),
            "schedule": stored.get("schedule", bank_def["schedule"]),
            "nombre":   bank_def["nombre"],
            "totp":     bank_def.get("totp", False),
            "campos":   bank_def["campos"],   # metadatos para renderizar el form
        }
        # Campos de credenciales: devolver el valor salvo si es secret
        for campo in bank_def["campos"]:
            key = campo["key"]
            if campo["type"] == "password":
                row[key]          = ""               # nunca devolver la contraseña
                row[f"has_{key}"] = bool(stored.get(key))
            elif campo["type"] == "checkbox":
                row[key] = bool(stored.get(key, False))
            else:
                row[key] = stored.get(key, "")

        result[banco] = row

    return result


# ── Para el scheduler (sin request context) ──────────────────────────────────

def find_all_enabled_configs() -> list[dict]:
    """
    Escanea /data/*/scraper_credentials.json y devuelve una lista de
    {banco, data_dir, config} para todos los scrapers habilitados en todos
    los directorios de usuario.

    Usado por el scheduler, que no tiene un request HTTP activo.
    """
    results = []
    pattern = os.path.join(_DATA_DIR, "*", _FILENAME)
    for creds_path in sorted(glob.glob(pattern)):
        data_dir = os.path.dirname(creds_path)
        try:
            with open(creds_path) as f:
                creds = json.load(f) or {}
            for banco, cfg in creds.items():
                if not isinstance(cfg, dict) or not cfg.get("enabled", False):
                    continue
                if banco not in BANKS:
                    continue
                full_cfg = dict(cfg)
                if "schedule" not in full_cfg:
                    full_cfg["schedule"] = BANKS[banco]["schedule"]
                results.append({
                    "banco":    banco,
                    "data_dir": data_dir,
                    "config":   full_cfg,
                })
        except Exception as exc:
            logger.warning("Error leyendo %s: %s", creds_path, exc)

    return results

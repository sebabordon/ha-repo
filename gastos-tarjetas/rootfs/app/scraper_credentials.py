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
        "password": "...",
        "tercer_dato": "APELLIDO",
        "schedule": "07:15"
      },
      ...
    }

Las contraseñas se almacenan en texto claro por ahora. El cifrado con clave
del addon se puede agregar en una versión futura (AES-GCM con la ADDON_SECRET
de config.yaml).
"""

import glob
import json
import logging
import os

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
            {"key": "usuario",     "label": "Usuario",        "type": "text",     "required": True},
            {"key": "password",    "label": "Contraseña",     "type": "password", "required": True},
            {"key": "tercer_dato", "label": "Tercer dato",    "type": "text",     "required": False,
             "hint": "Dato estático de seguridad (ej. apellido materno)"},
        ],
    },
    "galicia": {
        "nombre":   "Banco Galicia",
        "schedule": "07:30",
        "campos": [
            {"key": "usuario",  "label": "Usuario",     "type": "text",     "required": True},
            {"key": "password", "label": "Contraseña",  "type": "password", "required": True},
        ],
        "totp": True,   # requiere flujo TOTP interactivo para la primera sesión
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
                "hint":        "Cuántos días hacia atrás buscar movimientos (default: 60)",
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
    """Lee el JSON de credenciales del usuario. Devuelve {} si no existe."""
    path = _creds_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception as exc:
        logger.error("Error leyendo scraper_credentials.json: %s", exc)
        return {}


def write_creds(data: dict, data_dir: str | None = None) -> None:
    """Escribe el JSON de credenciales del usuario (reemplaza todo)."""
    path = _creds_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
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
                row[key]               = ""               # nunca devolver la contraseña
                row[f"has_{key}"]      = bool(stored.get(key))
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

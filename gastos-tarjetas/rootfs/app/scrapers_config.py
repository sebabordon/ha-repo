"""
Lee /data/scrapers.yaml y expone la configuración de cada scraper.

Formato esperado del archivo:

    owner_email: "seba@sbsoft.com.ar"   # usuario cuya DB se usa
    scrapers:
      amex:
        enabled: true
        usuario: "user@mail.com"
        password: "secret"
        schedule: "07:00"       # hora local HH:MM (corre todos los días)
      bbva:
        enabled: true
        usuario: "12345678"
        password: "secret"
        tercer_dato: "APELLIDO"
        schedule: "07:15"
      galicia:
        enabled: true
        usuario: "user"
        password: "secret"
        schedule: "07:30"
      mercadopago:
        enabled: true
        usuario: "user@mail.com"
        password: "secret"
        schedule: "07:45"
"""

import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.environ.get("DATA_DIR", "/data"), "scrapers.yaml")

# Horarios por defecto escalonados de 15 min para no saturar el RPi
_DEFAULT_SCHEDULES = {
    "amex":        "07:00",
    "bbva":        "07:15",
    "galicia":     "07:30",
    "mercadopago": "07:45",
}


def read_scrapers_config() -> dict:
    """Lee scrapers.yaml. Devuelve {} si el archivo no existe o es inválido."""
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as exc:
        logger.error("No se pudo leer scrapers.yaml: %s", exc)
        return {}


def get_scraper_config(banco: str) -> Optional[dict]:
    """Devuelve la config de un banco si está habilitado, o None."""
    data = read_scrapers_config()
    cfg = data.get("scrapers", {}).get(banco, {})
    if not cfg.get("enabled", False):
        return None
    # Inyectar horario por defecto si no está definido
    if "schedule" not in cfg:
        cfg = dict(cfg)
        cfg["schedule"] = _DEFAULT_SCHEDULES.get(banco, "07:00")
    return cfg


def get_all_enabled_scrapers() -> dict[str, dict]:
    """Devuelve {banco: config} para todos los scrapers habilitados."""
    data = read_scrapers_config()
    result = {}
    for banco, cfg in data.get("scrapers", {}).items():
        if cfg.get("enabled", False):
            if "schedule" not in cfg:
                cfg = dict(cfg)
                cfg["schedule"] = _DEFAULT_SCHEDULES.get(banco, "07:00")
            result[banco] = cfg
    return result


def get_owner_email() -> Optional[str]:
    """Email del usuario propietario de la DB donde se escriben los datos."""
    return read_scrapers_config().get("owner_email")


def is_configured() -> bool:
    """True si existe scrapers.yaml con al menos un scraper habilitado."""
    return bool(get_all_enabled_scrapers())

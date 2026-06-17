"""
Tipo de cambio dólar — fetch desde dolarapi.com, caché diario.

Sync (httpx.Client) para uso dentro de scrapers (thread pool).
"""
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE: dict = {}   # (tipo, date) → float

_TIPO_ALIAS = {
    "tarjeta": "tarjeta",
    "oficial": "oficial",
    "blue":    "blue",
}

_BASE_URL = "https://dolarapi.com/v1/dolares"


def fetch_tc_dolar(tipo: str = "tarjeta") -> Optional[float]:
    """
    Retorna el TC venta del dólar para el tipo dado (tarjeta/oficial/blue).
    Cachea el valor por tipo+día para no llamar la API en cada transacción.
    Devuelve None si la API no responde (nunca lanza excepción).
    """
    tipo = _TIPO_ALIAS.get(tipo, "tarjeta")
    key  = (tipo, date.today())
    if key in _CACHE:
        return _CACHE[key]
    try:
        import httpx
        with httpx.Client(timeout=8) as client:
            r = client.get(f"{_BASE_URL}/{tipo}")
            r.raise_for_status()
            data = r.json()
            tc = float(data.get("venta") or data.get("compra") or 0) or None
            if tc:
                _CACHE[key] = tc
            return tc
    except Exception as exc:
        logger.warning("[tc] fetch_tc_dolar(%s) failed: %s", tipo, exc)
        return None

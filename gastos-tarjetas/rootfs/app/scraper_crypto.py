"""
Encryption helpers para credenciales de scrapers.

Diseño con fallback graceful:
  - Si SCRAPER_ENCRYPTION_KEY (env var) está seteada Y `cryptography` se puede
    importar → encripta con Fernet (AES-128-CBC + HMAC-SHA256).
  - Si la var está seteada pero `cryptography` NO está instalada → loguea error
    y guarda plaintext (no rompe nada).
  - Si la var no está seteada → plaintext (default, comportamiento básico).

El flag `is_encrypted` se persiste en la DB junto con el ciphertext para que
cada fila se pueda descifrar independientemente del estado actual del env var.

Habilitar encryption en el add-on:
  1. `pip install cryptography` (o agregarlo a requirements.txt + rebuild)
  2. Setear `SCRAPER_ENCRYPTION_KEY=<string-cualquiera-largo-y-secreto>` en
     la config del add-on de HA (variables de entorno).
  3. Reiniciar el add-on. Las próximas escrituras quedan encriptadas; las
     viejas se siguen leyendo en plaintext hasta que se reescriban.

Rotación de key: requiere descifrar con la key vieja + re-escribir con la nueva.
No implementado todavía — el primer flujo es "set once".
"""

import logging
import os

logger = logging.getLogger(__name__)

_KEY_ENV = "SCRAPER_ENCRYPTION_KEY"


def _get_raw_key() -> str:
    return (os.environ.get(_KEY_ENV) or "").strip()


def _get_fernet():
    """
    Devuelve un objeto Fernet listo para usar, o None si no se puede encriptar.
    Loguea (una sola vez) los warnings de configuración.
    """
    raw = _get_raw_key()
    if not raw:
        return None
    try:
        import base64
        import hashlib
        from cryptography.fernet import Fernet
    except ImportError:
        if not _logged_missing_dep[0]:
            logger.error(
                "SCRAPER_ENCRYPTION_KEY está seteada pero el paquete "
                "`cryptography` no está instalado. Las credenciales se "
                "guardarán en PLAINTEXT. Instalá cryptography o quitá la "
                "env var para silenciar este aviso."
            )
            _logged_missing_dep[0] = True
        return None
    # Derivar una key Fernet (32 bytes b64-encoded) desde la entropía dada.
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


# flag mutable de módulo (lista para que sea referenciable en _get_fernet)
_logged_missing_dep = [False]


def is_encryption_available() -> bool:
    """True si hay env var Y dep cryptography importable."""
    return _get_fernet() is not None


def encrypt_str(plaintext: str) -> tuple[str, bool]:
    """
    Encripta `plaintext` si la encryption está disponible.
    Devuelve (data, is_encrypted_flag).
    Si no hay encryption disponible: (plaintext, False).
    """
    if plaintext is None:
        return ("", False)
    f = _get_fernet()
    if f is None:
        return (plaintext, False)
    try:
        token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return (token, True)
    except Exception as exc:
        logger.warning("encrypt_str falló (%s) — guardando plaintext", exc)
        return (plaintext, False)


def decrypt_str(data: str, is_encrypted: bool) -> str:
    """
    Descifra `data` si is_encrypted=True. Devuelve plaintext.
    Si is_encrypted=False, devuelve `data` tal cual.
    Si is_encrypted=True pero la key no está disponible, raise RuntimeError
    (mejor fallar fuerte que devolver basura ilegible).
    """
    if data is None or data == "":
        return ""
    if not is_encrypted:
        return data
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "Datos encriptados encontrados pero SCRAPER_ENCRYPTION_KEY no "
            "está disponible (o cryptography no está instalado). Configurá "
            "la env var con la misma key usada al encriptar."
        )
    return f.decrypt(data.encode("ascii")).decode("utf-8")

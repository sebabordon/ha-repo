"""
Per-user data directory context.

Each authenticated user gets their own data directory:
    /data/{sanitized_email}/

containing:  gastos.db  |  rules.yaml  |  match_rules.yaml

A ContextVar holds the active directory for the current request so that all
DB / file operations automatically use the right user's data without any
changes to their call signatures.

Usuarios nuevos:  arrancan con una DB limpia que siembra init_db() (schema +
cuentas default + categorías) y un rules.yaml copiado de los DEFAULTS bundleados
(default_rules.yaml).  NO se copia data legacy de /data/gastos.db ni de ningún
otro usuario: hacerlo (como hacía la migración vieja "el primero que loguea se
queda con todo") entregaba la data de un usuario a otro.  Para asignar data
legacy a un usuario puntual, copiala manualmente a su dir antes de su 1er login:
    cp /data/gastos.db /data/{sanitized_email}/gastos.db
"""

import os
import re
import shutil
from contextvars import ContextVar

# ── Base paths (fall back to env vars, mirroring config.py) ──────────────────
_DATA_DIR = os.environ.get("DATA_DIR", "/data")

# rules.yaml default bundleado (junto al código), para sembrar usuarios nuevos.
_BUNDLED_DEFAULT_RULES = os.path.join(os.path.dirname(__file__), "default_rules.yaml")

# ── Context variable ──────────────────────────────────────────────────────────
_user_data_dir: ContextVar[str | None] = ContextVar("user_data_dir", default=None)


def _sanitize(email: str) -> str:
    """Convert an e-mail address to a safe directory name."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email.lower())


# ── Public getters ────────────────────────────────────────────────────────────

def get_data_dir() -> str:
    """Return the active user data directory, or the global default."""
    d = _user_data_dir.get()
    return d if d is not None else _DATA_DIR


def get_db_path() -> str:
    return os.path.join(get_data_dir(), "gastos.db")


def get_rules_file() -> str:
    return os.path.join(get_data_dir(), "rules.yaml")


def get_match_rules_file() -> str:
    return os.path.join(get_data_dir(), "match_rules.yaml")


# ── Context management ────────────────────────────────────────────────────────

def set_user_context(email: str):
    """
    Point the context at *email*'s data directory, creating it if needed.

    Para un usuario nuevo siembra su rules.yaml desde los defaults bundleados
    (para que tenga las categorías por defecto).  NUNCA copia data de otro
    usuario ni de /data/gastos.db raíz — la DB la crea limpia init_db().

    Returns a ContextVar token — call reset_user_context(token) when done.
    """
    user_dir = os.path.join(_DATA_DIR, _sanitize(email))
    os.makedirs(user_dir, exist_ok=True)

    # Set context BEFORE init_db() (que lo llama el middleware después) vea el path.
    token = _user_data_dir.set(user_dir)

    # Seed rules.yaml default para usuarios nuevos (no-op si ya existe).
    dest_rules = os.path.join(user_dir, "rules.yaml")
    if not os.path.exists(dest_rules) and os.path.exists(_BUNDLED_DEFAULT_RULES):
        try:
            shutil.copy2(_BUNDLED_DEFAULT_RULES, dest_rules)
        except OSError:
            pass  # no-fatal — categorizer trata rules.yaml ausente como vacío

    return token


def reset_user_context(token) -> None:
    """Restore the previous context (call in a finally block)."""
    _user_data_dir.reset(token)

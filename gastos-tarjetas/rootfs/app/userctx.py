"""
Per-user data directory context.

Each authenticated user gets their own data directory:
    /data/{sanitized_email}/

containing:  gastos.db  |  rules.yaml  |  match_rules.yaml

A ContextVar holds the active directory for the current request so that all
DB / file operations automatically use the right user's data without any
changes to their call signatures.

Migration:  on the user's very first request we copy any root-level legacy
files (/data/gastos.db, rules.yaml, match_rules.yaml) into their directory
so that existing data is preserved seamlessly.
"""

import os
import re
import shutil
from contextvars import ContextVar

# ── Base paths (fall back to env vars, mirroring config.py) ──────────────────
_DATA_DIR        = os.environ.get("DATA_DIR",        "/data")
_DEFAULT_DB      = os.path.join(_DATA_DIR, "gastos.db")
_DEFAULT_RULES   = os.environ.get("RULES_FILE",       os.path.join(_DATA_DIR, "rules.yaml"))
_DEFAULT_MATCH   = os.environ.get("MATCH_RULES_FILE", os.path.join(_DATA_DIR, "match_rules.yaml"))

# Sentinel written after legacy data is migrated to the first user's directory.
# Its presence tells us NOT to copy root-level files for any subsequent user
# (they would otherwise inherit another user's data).
_MIGRATED_SENTINEL = os.path.join(_DATA_DIR, ".migrated_to_per_user")

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
    Point the context at *email*'s data directory.

    Creates the directory if needed and copies any existing root-level data
    files (one-time migration for legacy single-user installations).

    Returns a ContextVar token — call reset_user_context(token) when done.
    """
    user_dir = os.path.join(_DATA_DIR, _sanitize(email))
    os.makedirs(user_dir, exist_ok=True)

    # Set context BEFORE migration so init_db() also sees the right path
    token = _user_data_dir.set(user_dir)

    # One-time legacy migration: copy root-level files to this user's directory.
    # Only runs if the sentinel doesn't exist yet — once the first user's data
    # has been migrated we write the sentinel so that any NEW users who register
    # afterwards start with an empty DB instead of inheriting existing data.
    if not os.path.exists(_MIGRATED_SENTINEL):
        copied_any = False
        for src, fname in [
            (_DEFAULT_DB,    "gastos.db"),
            (_DEFAULT_RULES, "rules.yaml"),
            (_DEFAULT_MATCH, "match_rules.yaml"),
        ]:
            dest = os.path.join(user_dir, fname)
            if not os.path.exists(dest) and os.path.exists(src):
                try:
                    shutil.copy2(src, dest)
                    copied_any = True
                except OSError:
                    pass  # non-fatal — DB will be created fresh by init_db()

        if copied_any:
            # Mark migration done so future new users don't get a copy of this data
            try:
                with open(_MIGRATED_SENTINEL, "w") as f:
                    f.write(email + "\n")
            except OSError:
                pass

    return token


def reset_user_context(token) -> None:
    """Restore the previous context (call in a finally block)."""
    _user_data_dir.reset(token)

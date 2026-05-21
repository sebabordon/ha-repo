import hashlib
import json
import os
from fastapi import HTTPException, Request

from config import DATA_DIR, ALLOWED_DOMAIN, REGISTRATION_ENABLED_DEFAULT, ADMIN_PASSWORD

USERS_FILE    = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ADMIN_EMAIL   = f"admin@{ALLOWED_DOMAIN}"


# ── Settings (runtime overrides stored in /data/settings.json) ────────────────

def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(s: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


def get_registration_enabled() -> bool:
    s = _load_settings()
    if "registration_enabled" in s:
        return bool(s["registration_enabled"])
    return REGISTRATION_ENABLED_DEFAULT


def set_registration_enabled(val: bool):
    s = _load_settings()
    s["registration_enabled"] = val
    _save_settings(s)


# ── Users ──────────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_users(users: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()


def verify_password(email: str, password: str) -> bool:
    users = _load_users()
    entry = users.get(email)
    if not entry:
        return False
    return _hash(password, entry["salt"]) == entry["hash"]


def verify_admin(email: str, password: str) -> bool:
    """Returns True if email is the admin address and password matches ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        return False
    return email.lower() == ADMIN_EMAIL and password == ADMIN_PASSWORD


def create_user(email: str, password: str) -> tuple[bool, str]:
    """Returns (ok, error_msg)."""
    if not get_registration_enabled():
        return False, "El registro de nuevos usuarios está deshabilitado."
    if not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        return False, f"Solo se permiten emails @{ALLOWED_DOMAIN}"
    if email.lower() == ADMIN_EMAIL:
        return False, "Ese email no está disponible."
    users = _load_users()
    if email in users:
        return False, "El usuario ya existe"
    salt = os.urandom(16).hex()
    users[email] = {"hash": _hash(password, salt), "salt": salt}
    _save_users(users)
    return True, ""


def list_users() -> list[str]:
    return sorted(_load_users().keys())


def delete_user(email: str) -> bool:
    users = _load_users()
    if email not in users:
        return False
    del users[email]
    _save_users(users)
    return True


def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    users = _load_users()
    if email not in users:
        return False, "Usuario no encontrado."
    salt = os.urandom(16).hex()
    users[email] = {"hash": _hash(new_password, salt), "salt": salt}
    _save_users(users)
    return True, ""


def require_auth(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user

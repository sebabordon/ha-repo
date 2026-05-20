import hashlib
import json
import os
from fastapi import HTTPException, Request

from config import DATA_DIR, ALLOWED_DOMAIN

USERS_FILE = os.path.join(DATA_DIR, "users.json")


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


def create_user(email: str, password: str) -> tuple[bool, str]:
    """Returns (ok, error_msg)."""
    if not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        return False, f"Solo se permiten emails @{ALLOWED_DOMAIN}"
    users = _load_users()
    if email in users:
        return False, "El usuario ya existe"
    salt = os.urandom(16).hex()
    users[email] = {"hash": _hash(password, salt), "salt": salt}
    _save_users(users)
    return True, ""


def require_auth(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user

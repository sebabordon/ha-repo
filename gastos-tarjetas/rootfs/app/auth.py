import hashlib
import hmac
import json
import os
import secrets
from fastapi import HTTPException, Request

from config import DATA_DIR, ALLOWED_DOMAIN, REGISTRATION_ENABLED_DEFAULT, ADMIN_PASSWORD

USERS_FILE          = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE       = os.path.join(DATA_DIR, "settings.json")
SESSION_TOKENS_FILE = os.path.join(DATA_DIR, "session_tokens.json")
ADMIN_EMAIL         = f"admin@{ALLOWED_DOMAIN}"

# Máximo de sesiones activas (tokens) por usuario. Cada login agrega una; el
# logout la quita. Limita el crecimiento si las cookies expiran sin logout.
# IMPORTANTE: al superar el tope se expulsa el token MÁS VIEJO aunque siga
# activo → esa sesión se desloguea. Por eso el valor debe holgar varios
# dispositivos × varias re-logueadas; 10 era muy bajo (iPhone PWA + desktop +
# re-logins dejaban afuera sesiones vivas).
_MAX_TOKENS_PER_USER = 50


def _atomic_write_json(path: str, obj) -> None:
    """Escribe JSON de forma atómica (tmp + os.replace).

    Evita que un lector concurrente —o un reinicio del add-on a mitad de
    escritura— vea el archivo truncado (que `json.load` interpretaría como
    corrupto y, en el caso de session_tokens.json, desloguearía a todos).
    `os.replace` es atómico dentro del mismo filesystem.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


# ── Settings (runtime overrides stored in /data/settings.json) ────────────────

def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(s: dict):
    _atomic_write_json(SETTINGS_FILE, s)


def get_registration_enabled() -> bool:
    s = _load_settings()
    if "registration_enabled" in s:
        return bool(s["registration_enabled"])
    return REGISTRATION_ENABLED_DEFAULT


def set_registration_enabled(val: bool):
    s = _load_settings()
    s["registration_enabled"] = val
    _save_settings(s)


# ── Session tokens (validación server-side de la sesión) ──────────────────────
# La sesión vive en una cookie firmada, pero la firma por sí sola no permite
# invalidar una sesión (un logout solo le pide al navegador que borre la cookie;
# si no la borra, la cookie vieja sigue autenticando). Para que el logout corte
# de verdad guardamos, por usuario, el set de tokens de sesión activos. Cada
# cookie lleva su token (`stoken`); en cada request validamos que el token siga
# en el set. El logout quita el token de ESTE dispositivo; reset de password y
# borrado de usuario quitan TODOS (cierran sesión en todos lados).

def _load_session_tokens() -> dict:
    try:
        with open(SESSION_TOKENS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_session_tokens(d: dict):
    _atomic_write_json(SESSION_TOKENS_FILE, d)


def issue_session_token(email: str) -> str:
    """Crea un token de sesión nuevo para *email* y lo agrega al set activo."""
    email = email.lower()
    d = _load_session_tokens()
    tokens = d.get(email, [])
    token = secrets.token_urlsafe(32)
    tokens.append(token)
    if len(tokens) > _MAX_TOKENS_PER_USER:
        tokens = tokens[-_MAX_TOKENS_PER_USER:]
    d[email] = tokens
    _save_session_tokens(d)
    return token


def revoke_session_token(email: str, token: str) -> None:
    """Revoca un token puntual (logout de este dispositivo)."""
    if not email or not token:
        return
    email = email.lower()
    d = _load_session_tokens()
    tokens = d.get(email, [])
    if token in tokens:
        tokens.remove(token)
        d[email] = tokens
        _save_session_tokens(d)


def revoke_all_session_tokens(email: str) -> None:
    """Revoca todas las sesiones del usuario (reset de password / borrado)."""
    if not email:
        return
    email = email.lower()
    d = _load_session_tokens()
    if email in d:
        d.pop(email, None)
        _save_session_tokens(d)


def is_session_token_valid(email: str, token: str) -> bool:
    """True si *token* está en el set activo de *email*."""
    if not email or not token:
        return False
    d = _load_session_tokens()
    return token in d.get(email.lower(), [])


# ── Users ──────────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_users(users: dict):
    _atomic_write_json(USERS_FILE, users)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()


def verify_password(email: str, password: str) -> bool:
    users = _load_users()
    entry = users.get(email)
    if not entry:
        return False
    # compare_digest: comparación de tiempo constante para no filtrar info del
    # hash vía timing (igual que verify_admin).
    return hmac.compare_digest(_hash(password, entry["salt"]), entry["hash"])


def verify_admin(email: str, password: str) -> bool:
    """Returns True if email is the admin address and password matches ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        return False
    return email.lower() == ADMIN_EMAIL and hmac.compare_digest(password, ADMIN_PASSWORD)


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
    # Invalidar cualquier sesión activa del usuario borrado.
    revoke_all_session_tokens(email)
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
    # Cambiar la contraseña cierra todas las sesiones abiertas del usuario.
    revoke_all_session_tokens(email)
    return True, ""


def require_auth(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not is_session_token_valid(user.get("email", ""), user.get("stoken", "")):
        # Cookie revocada o anterior al esquema de tokens → forzar re-login.
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sesión expirada")
    return user

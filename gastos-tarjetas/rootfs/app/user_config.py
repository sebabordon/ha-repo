"""
User configuration: managed users list and source→user default mapping.
Stored in {user_data_dir}/user_config.json (persists across restarts).
"""
import json
import os

from userctx import get_data_dir


def _user_config_path() -> str:
    return os.path.join(get_data_dir(), "user_config.json")

_DEFAULT_CONFIG: dict = {
    "usuarios": ["Titular", "Adicional"],
    "fuente_usuario": {
        "amex":        "Titular",
        "bbva_mc":     "Titular",
        "bbva_visa":   "Titular",
        "bbva_cuenta": "Titular",
        "galicia_mc":  "Titular",
        "mercadopago": "Titular",
    },
    "reglas_usuario": [],
}


def read_user_config() -> dict:
    path = _user_config_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            # Ensure required keys exist
            if "usuarios" not in data:
                data["usuarios"] = list(_DEFAULT_CONFIG["usuarios"])
            if "fuente_usuario" not in data:
                data["fuente_usuario"] = dict(_DEFAULT_CONFIG["fuente_usuario"])
            if "reglas_usuario" not in data:
                data["reglas_usuario"] = []
            return data
        except Exception:
            pass
    return {
        "usuarios":       list(_DEFAULT_CONFIG["usuarios"]),
        "fuente_usuario": dict(_DEFAULT_CONFIG["fuente_usuario"]),
        "reglas_usuario": [],
    }


def write_user_config(data: dict) -> None:
    path = _user_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

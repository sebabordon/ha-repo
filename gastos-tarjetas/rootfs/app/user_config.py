"""
User configuration: managed users list and source→user default mapping.
Stored in /data/user_config.json (persists across restarts).
"""
import json
import os

_USER_CONFIG_PATH = "/data/user_config.json"

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
}


def read_user_config() -> dict:
    if os.path.exists(_USER_CONFIG_PATH):
        try:
            with open(_USER_CONFIG_PATH) as f:
                data = json.load(f)
            # Ensure required keys exist
            if "usuarios" not in data:
                data["usuarios"] = list(_DEFAULT_CONFIG["usuarios"])
            if "fuente_usuario" not in data:
                data["fuente_usuario"] = dict(_DEFAULT_CONFIG["fuente_usuario"])
            return data
        except Exception:
            pass
    return {
        "usuarios":       list(_DEFAULT_CONFIG["usuarios"]),
        "fuente_usuario": dict(_DEFAULT_CONFIG["fuente_usuario"]),
    }


def write_user_config(data: dict) -> None:
    dir_ = os.path.dirname(_USER_CONFIG_PATH)
    if dir_:
        os.makedirs(dir_, exist_ok=True)
    with open(_USER_CONFIG_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    # Mapeo titular de tarjeta → persona. Las claves son el texto exacto del
    # cardholder tal como aparece en el resumen (ej. "SEBASTIAN ALB - 11005").
    # Se resuelve al importar movimientos del scraper, ANTES del default por
    # fuente, para que tarjetas con varios titulares (ej. AMEX adicionales)
    # asignen la persona correcta. Editable en Config → Usuarios.
    "cardholder_usuario": {},
    "pwa_shortcuts": [],
    # Ciclo de cobro (período contable ≠ mes calendario). Inactivo por defecto:
    # cuando está apagado, todos los agregados usan el mes calendario como siempre.
    # Modelo delta: los últimos `periodo_delta_dias` días de cada mes cuentan
    # para el período del mes siguiente. Overrides {YYYY-MM: delta} por mes.
    "periodo_activo": False,
    "periodo_delta_dias": 2,
    "periodo_overrides": {},
    # Confirmación heurística de pago en el widget de vencimientos. Marca el
    # badge amarillo "pago probable" cuando hay un gasto 'Pago de Tarjeta' cerca
    # del vencimiento que matchea el saldo del resumen, aunque no exista un
    # emparejado explícito. Ver list_vencimientos() en db.py.
    "venc_pago_match_activo": True,
    "venc_pago_match_dias": 8,           # ventana ± días alrededor del vencimiento
    "venc_pago_match_tol_ars": 5000.0,   # tolerancia en pesos (saldo ARS sin RG 5617)
    "venc_pago_match_tol_usd": 1.0,      # tolerancia en dólares (saldo USD)
    # Categorías que cuentan como "pago de tarjeta" para el badge amarillo. Un
    # pago a veces queda categorizado como transferencia en vez de Pago de
    # Tarjeta; agregá esas categorías acá desde la UI si querés que cuenten.
    "venc_pago_match_categorias": ["Pago de Tarjeta"],
    # Aviso push de vencimientos de tarjeta (feature b1). Opt-in: apagado hasta
    # que el usuario lo prenda. `dias_antes` son los umbrales de antelación (manda
    # un push cuando faltan exactamente N días para un vencimiento IMPAGO); `hora`
    # es la hora local (ART) en que se manda. La dedup vive en venc_notificaciones.
    "venc_notif_activo": False,
    "venc_notif_dias_antes": [3, 1],
    "venc_notif_hora": 9,
    # Patrones (substring, case-insensitive) que identifican un crédito de tarjeta
    # como PAGO / acreditación / percepción / ajuste — es decir, algo que NO es un
    # gasto del período. Se aplican SOLO a movimientos con monto < 0: si la
    # descripción matchea, el crédito se ignora (es un pago); si NO matchea, el
    # crédito se RESTA del consumo (es un reintegro de comercio, ej. devolución de
    # una compra). Los cargos (monto > 0) siempre cuentan. Usado por
    # _apply_tarjeta_consumo() para que el consumo del widget matchee el total de
    # "Cargos" que muestra el banco. Editable en Config → Importación.
    "tarjeta_consumo_pago_patrones": ["PAGO", "ACREDITAC", "AJUSTE", "PERCEPCION", "RG 5617"],
    # ── Categorización por IA (configurable desde la UI) ─────────────────────
    # Lista de categorías sugeridas que se inyectan en el prompt, y el template
    # del prompt mismo. {categorias} y {desc} son los placeholders disponibles.
    "categorizer_categorias": [
        "Supermercado", "Combustible", "Restaurante", "Farmacia",
        "Entretenimiento", "Viajes", "Ropa", "Tecnología", "Servicios", "Otros",
    ],
    "categorizer_prompt": (
        "Categoriza este gasto de tarjeta de crédito argentina en una sola "
        "palabra o frase corta (ej: {categorias}).\n"
        "Gasto: {desc}\n"
        "Responde solo con la categoría, sin explicación."
    ),
    # ── Categorías especiales fijas (excluidas de totales/gráficos) ──────────
    # Antes hardcodeadas en db.py (_BUILTIN_SPECIALS). Editables desde la UI;
    # se mergean con las marcadas "Especial" en la tabla categorias y rules.yaml.
    "categorias_especiales_builtin": [
        "Transferencia", "Transferencia Intercuentas", "Pago de Tarjeta",
    ],
    # ── Tipo de cambio USD para presupuesto ──────────────────────────────────
    # Tipo de cotización a usar al convertir presupuestos/gastos en USD a ARS.
    # Valores: "tarjeta" (oficial + impuestos, default), "oficial", "blue".
    "tc_dolar_tipo": "tarjeta",
    # ── Paleta de íconos PWA por fuente (color de fondo + siglas) ────────────
    # Antes hardcodeada en main.py (_FUENTE_ICON_STYLES). Cada entrada:
    #   {"bg": "#RRGGBB", "fg": "#RRGGBB", "lines": ["LIN1", "LIN2"]}
    "fuente_icon_styles": {
        "amex":        {"bg": "#016FD0", "lines": ["AMEX"],         "fg": "#FFFFFF"},
        "mercadopago": {"bg": "#009EE3", "lines": ["MP"],           "fg": "#FFFFFF"},
        "bbva_mc":     {"bg": "#004481", "lines": ["BBVA", "MC"],   "fg": "#FFFFFF"},
        "bbva_visa":   {"bg": "#004481", "lines": ["BBVA", "VISA"], "fg": "#FFFFFF"},
        "bbva_cuenta": {"bg": "#004481", "lines": ["BBVA", "CTA"],  "fg": "#FFFFFF"},
        "galicia_mc":  {"bg": "#E31837", "lines": ["GAL", "MC"],    "fg": "#FFFFFF"},
    },
}


def config_default(key: str):
    """Default de una clave de config (para que otros módulos no la redefinan)."""
    import copy
    return copy.deepcopy(_DEFAULT_CONFIG.get(key))


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
            if "cardholder_usuario" not in data:
                data["cardholder_usuario"] = {}
            if "pwa_shortcuts" not in data:
                data["pwa_shortcuts"] = []
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

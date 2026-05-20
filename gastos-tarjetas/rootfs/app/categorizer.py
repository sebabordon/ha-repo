import re
import yaml
from typing import Optional

from config import RULES_FILE, CLAUDE_API_KEY


def load_rules() -> list[dict]:
    try:
        with open(RULES_FILE) as f:
            data = yaml.safe_load(f) or {}
        return data.get("reglas", [])
    except (FileNotFoundError, yaml.YAMLError):
        return []


def categorize_by_rules(descripcion: str) -> Optional[str]:
    for regla in load_rules():
        palabras = regla.get("palabras", [])
        if palabras:
            pattern = "(?i)(" + "|".join(re.escape(str(p)) for p in palabras) + ")"
        elif "patron" in regla:
            pattern = regla["patron"]  # backward compat with old regex format
        else:
            continue
        try:
            if re.search(pattern, descripcion):
                return regla["categoria"]
        except re.error:
            continue
    return None


async def categorize_by_claude(descripcion: str) -> Optional[str]:
    if not CLAUDE_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": (
                    f"Categoriza este gasto de tarjeta de crédito argentina en una sola palabra o frase corta "
                    f"(ej: Supermercado, Combustible, Restaurante, Farmacia, Entretenimiento, Viajes, Ropa, Tecnología, Servicios, Otros).\n"
                    f"Gasto: {descripcion}\n"
                    f"Responde solo con la categoría, sin explicación."
                ),
            }],
        )
        return msg.content[0].text.strip()
    except Exception:
        return None


async def categorize(descripcion: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (categoria, fuente) where fuente is 'regla', 'claude', or None."""
    cat = categorize_by_rules(descripcion)
    if cat:
        return cat, "regla"
    cat = await categorize_by_claude(descripcion)
    if cat:
        return cat, "claude"
    return None, None

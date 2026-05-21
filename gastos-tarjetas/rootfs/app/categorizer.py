import re
import yaml
from typing import Optional

from config import RULES_FILE, CLAUDE_API_KEY, GROQ_API_KEY, GEMINI_API_KEY

_PROMPT = (
    "Categoriza este gasto de tarjeta de crédito argentina en una sola palabra o frase corta "
    "(ej: Supermercado, Combustible, Restaurante, Farmacia, Entretenimiento, Viajes, Ropa, "
    "Tecnología, Servicios, Otros).\n"
    "Gasto: {desc}\n"
    "Responde solo con la categoría, sin explicación."
)


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


async def _openai_compat_call(url: str, key: str, model: str, content: str) -> Optional[str]:
    """Generic helper for any OpenAI-compatible chat completions endpoint."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": content}],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


async def categorize_by_groq(descripcion: str) -> Optional[str]:
    """Groq free API — llama-3.1-8b-instant, ~14k req/day."""
    if not GROQ_API_KEY:
        return None
    return await _openai_compat_call(
        "https://api.groq.com/openai/v1/chat/completions",
        GROQ_API_KEY, "llama-3.1-8b-instant",
        _PROMPT.format(desc=descripcion),
    )


async def categorize_by_gemini(descripcion: str) -> Optional[str]:
    """Google Gemini free API — gemini-2.0-flash, ~1500 req/day."""
    if not GEMINI_API_KEY:
        return None
    return await _openai_compat_call(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        GEMINI_API_KEY, "gemini-2.0-flash",
        _PROMPT.format(desc=descripcion),
    )


async def categorize_by_claude(descripcion: str) -> Optional[str]:
    if not CLAUDE_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": _PROMPT.format(desc=descripcion)}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return None


async def categorize(descripcion: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (categoria, fuente). Tries: reglas → Groq → Gemini → Claude."""
    cat = categorize_by_rules(descripcion)
    if cat:
        return cat, "regla"
    if GROQ_API_KEY:
        cat = await categorize_by_groq(descripcion)
        if cat:
            return cat, "groq"
    if GEMINI_API_KEY:
        cat = await categorize_by_gemini(descripcion)
        if cat:
            return cat, "gemini"
    if CLAUDE_API_KEY:
        cat = await categorize_by_claude(descripcion)
        if cat:
            return cat, "claude"
    return None, None

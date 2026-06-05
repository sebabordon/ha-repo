import os
import re
import yaml
from typing import Optional

from config import CLAUDE_API_KEY, GROQ_API_KEY, GEMINI_API_KEY
from userctx import get_rules_file

def _build_prompt(descripcion: str) -> str:
    """Construye el prompt de categorización desde la config del usuario.

    El template (`categorizer_prompt`) y la lista de categorías sugeridas
    (`categorizer_categorias`) son editables desde la UI (Config → Categorización).
    Solo se invoca en el camino IA (cuando ninguna regla matcheó), así que el
    read del config es despreciable frente a la llamada HTTP que sigue.
    """
    from user_config import read_user_config, config_default
    try:
        cfg = read_user_config()
    except Exception:
        cfg = {}
    cats     = cfg.get("categorizer_categorias") or config_default("categorizer_categorias")
    template = cfg.get("categorizer_prompt")     or config_default("categorizer_prompt")
    try:
        return template.format(categorias=", ".join(cats), desc=descripcion)
    except (KeyError, IndexError):
        # Template inválido (placeholder desconocido) → fallback al default.
        return config_default("categorizer_prompt").format(
            categorias=", ".join(cats), desc=descripcion)

# ── Rules cache ───────────────────────────────────────────────────────────────
_rules_cache: dict = {"rules": None, "mtime": -1.0}


def load_rules() -> list[dict]:
    path = get_rules_file()
    try:
        mtime = os.path.getmtime(path)
        if _rules_cache["mtime"] == mtime and _rules_cache["rules"] is not None:
            return _rules_cache["rules"]
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("reglas", [])
        _rules_cache["mtime"] = mtime
        _rules_cache["rules"] = rules
        return rules
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return []


def _invalidate_rules_cache() -> None:
    _rules_cache["mtime"] = -1.0
    _rules_cache["rules"] = None


def categorize_by_rules(
    descripcion: str,
    monto: float = 0.0,
    fuente: str = "",
) -> Optional[str]:
    for regla in load_rules():
        # Fuentes filter
        fuentes = regla.get("fuentes", [])
        if fuentes and fuente and fuente not in fuentes:
            continue
        # solo_egresos filter
        if regla.get("solo_egresos") and monto <= 0:
            continue

        palabras = regla.get("palabras", [])
        if palabras:
            # (?<!\w)/(?!\w) lookarounds prevent partial matches ("coto" in "PSICOTOLOGO")
            # and also work when keywords start/end with non-word chars like %, =, *, etc.
            pattern = "(?i)(" + "|".join(r"(?<!\w)" + re.escape(str(p)) + r"(?!\w)" for p in palabras) + ")"
        elif regla.get("patron"):
            pattern = regla["patron"]  # backward compat with old regex format
        else:
            continue
        try:
            if re.search(pattern, descripcion):
                return regla["categoria"]
        except (re.error, TypeError):
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


async def categorize_by_groq(prompt: str) -> Optional[str]:
    """Groq free API — llama-3.1-8b-instant, ~14k req/day."""
    if not GROQ_API_KEY:
        return None
    return await _openai_compat_call(
        "https://api.groq.com/openai/v1/chat/completions",
        GROQ_API_KEY, "llama-3.1-8b-instant",
        prompt,
    )


async def categorize_by_gemini(prompt: str) -> Optional[str]:
    """Google Gemini free API — gemini-2.0-flash, ~1500 req/day."""
    if not GEMINI_API_KEY:
        return None
    return await _openai_compat_call(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        GEMINI_API_KEY, "gemini-2.0-flash",
        prompt,
    )


async def categorize_by_claude(prompt: str) -> Optional[str]:
    if not CLAUDE_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return None


def auto_add_keyword_to_rule(descripcion: str, categoria: str) -> bool:
    """
    Add `descripcion` as a keyword to the rule for `categoria`.
    Creates the rule if it doesn't exist yet.
    Returns True if rules were modified.
    """
    if not descripcion or not categoria:
        return False
    try:
        with open(get_rules_file()) as f:
            data = yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        data = {}

    reglas = data.get("reglas", [])

    # Find rule for this category
    target = next((r for r in reglas if r.get("categoria") == categoria), None)
    if target is None:
        target = {"categoria": categoria, "palabras": []}
        reglas.append(target)

    palabras = target.setdefault("palabras", [])
    if descripcion in palabras:
        return False   # already there

    palabras.append(descripcion)
    data["reglas"] = reglas
    with open(get_rules_file(), "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    _invalidate_rules_cache()
    return True


async def categorize(descripcion: str, monto: float = 0.0, fuente: str = "") -> tuple[Optional[str], Optional[str]]:
    """Returns (categoria, fuente). Tries: reglas → Groq → Gemini → Claude."""
    cat = categorize_by_rules(descripcion, monto=monto, fuente=fuente)
    if cat:
        return cat, "regla"
    # Camino IA: construimos el prompt (desde config) una sola vez.
    prompt = _build_prompt(descripcion)
    if GROQ_API_KEY:
        cat = await categorize_by_groq(prompt)
        if cat:
            return cat, "groq"
    if GEMINI_API_KEY:
        cat = await categorize_by_gemini(prompt)
        if cat:
            return cat, "gemini"
    if CLAUDE_API_KEY:
        cat = await categorize_by_claude(prompt)
        if cat:
            return cat, "claude"
    return None, None

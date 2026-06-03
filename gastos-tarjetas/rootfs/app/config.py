import os

APP_VERSION = "0.5.112"

CLAUDE_API_KEY  = os.environ.get("CLAUDE_API_KEY",  "").strip()
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY",    "").strip()
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY",  "").strip()
ALLOWED_DOMAIN  = os.environ.get("ALLOWED_DOMAIN",  "example.com")
# Optional: first name (or partial name) of the secondary cardholder as it
# appears in AMEX/BBVA PDF section headers. When set, those sections are
# tagged with usuario="Adicional"; all other transactions use "Titular".
TITULAR2_NAME   = os.environ.get("TITULAR2_NAME",   "").strip()
DATA_DIR = os.environ.get("DATA_DIR", "/data")
RULES_FILE       = os.environ.get("RULES_FILE",       "/data/rules.yaml")
MATCH_RULES_FILE = os.environ.get("MATCH_RULES_FILE", "/data/match_rules.yaml")
DB_PATH = os.path.join(DATA_DIR, "gastos.db")

# Registration & admin
_reg_env = os.environ.get("REGISTRATION_ENABLED", "false").lower()
REGISTRATION_ENABLED_DEFAULT = _reg_env in ("1", "true", "yes")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()

#!/usr/bin/with-contenv bashio

export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export GROQ_API_KEY=$(bashio::config 'groq_api_key')
export GEMINI_API_KEY=$(bashio::config 'gemini_api_key')
export ALLOWED_DOMAIN=$(bashio::config 'allowed_domain')
export REGISTRATION_ENABLED=$(bashio::config 'registration_enabled')
export ADMIN_PASSWORD=$(bashio::config 'admin_password')
export TITULAR2_NAME=$(bashio::config 'titular2_name')
export SCRAPER_ENCRYPTION_KEY=$(bashio::config 'scraper_encryption_key')
export DATA_DIR="/data"
export RULES_FILE="/data/rules.yaml"

mkdir -p "${DATA_DIR}"

# Generar SESSION_SECRET al primer arranque y persistirlo para que las
# sesiones sobrevivan reinicios del add-on.
SESSION_SECRET_FILE="${DATA_DIR}/session_secret"
if [ ! -f "${SESSION_SECRET_FILE}" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${SESSION_SECRET_FILE}"
    chmod 600 "${SESSION_SECRET_FILE}"
    bashio::log.info "SESSION_SECRET generado y guardado."
fi
export SESSION_SECRET=$(cat "${SESSION_SECRET_FILE}")

if [ ! -f "${RULES_FILE}" ]; then
    cp /app/default_rules.yaml "${RULES_FILE}"
elif ! python3 -c "import yaml; yaml.safe_load(open('${RULES_FILE}'))" 2>/dev/null; then
    bashio::log.warning "rules.yaml tiene errores de sintaxis, reemplazando con valores por defecto..."
    cp /app/default_rules.yaml "${RULES_FILE}"
fi

bashio::log.info "Starting Gastos on port 8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-config /app/log_config.json

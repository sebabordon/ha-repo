#!/usr/bin/with-contenv bashio

export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export GROQ_API_KEY=$(bashio::config 'groq_api_key')
export ALLOWED_DOMAIN=$(bashio::config 'allowed_domain')
export REGISTRATION_ENABLED=$(bashio::config 'registration_enabled')
export ADMIN_PASSWORD=$(bashio::config 'admin_password')
export DATA_DIR="/data"
export RULES_FILE="/data/rules.yaml"

mkdir -p "${DATA_DIR}"

if [ ! -f "${RULES_FILE}" ]; then
    cp /app/default_rules.yaml "${RULES_FILE}"
elif ! python3 -c "import yaml; yaml.safe_load(open('${RULES_FILE}'))" 2>/dev/null; then
    bashio::log.warning "rules.yaml tiene errores de sintaxis, reemplazando con valores por defecto..."
    cp /app/default_rules.yaml "${RULES_FILE}"
fi

bashio::log.info "Starting Gastos Tarjetas on port 8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000

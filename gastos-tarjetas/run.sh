#!/usr/bin/with-contenv bashio

export GOOGLE_CLIENT_ID=$(bashio::config 'google_client_id')
export GOOGLE_CLIENT_SECRET=$(bashio::config 'google_client_secret')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export ALLOWED_DOMAIN=$(bashio::config 'allowed_domain')
export DATA_DIR="/data"
export RULES_FILE="/data/rules.yaml"

mkdir -p "${DATA_DIR}"

# Copy default rules if not present
if [ ! -f "${RULES_FILE}" ]; then
    cp /app/default_rules.yaml "${RULES_FILE}"
fi

bashio::log.info "Starting Gastos Tarjetas on port 8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000

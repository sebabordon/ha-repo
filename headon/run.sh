#!/usr/bin/with-contenv bashio

export ALLOWED_DOMAIN=$(bashio::config 'allowed_domain')
export REGISTRATION_ENABLED=$(bashio::config 'registration_enabled')
export ADMIN_PASSWORD=$(bashio::config 'admin_password')
export DATA_DIR="/data"

mkdir -p "${DATA_DIR}"

SESSION_SECRET_FILE="${DATA_DIR}/session_secret"
if [ ! -f "${SESSION_SECRET_FILE}" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${SESSION_SECRET_FILE}"
    chmod 600 "${SESSION_SECRET_FILE}"
    bashio::log.info "SESSION_SECRET generado y guardado."
fi
export SESSION_SECRET=$(cat "${SESSION_SECRET_FILE}")

bashio::log.info "Starting HeadOn on port 8100..."
exec uvicorn main:app --host 0.0.0.0 --port 8100

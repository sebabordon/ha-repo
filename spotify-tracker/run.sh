#!/usr/bin/with-contenv bashio

export SPOTIFY_CLIENT_ID=$(bashio::config 'spotify_client_id')
export SPOTIFY_CLIENT_SECRET=$(bashio::config 'spotify_client_secret')
export REDIRECT_URI=$(bashio::config 'redirect_uri')
export SCAN_DAY=$(bashio::config 'scan_day')
export SCAN_HOUR=$(bashio::config 'scan_hour')
export DATA_DIR="/data"
export AUTH_USER=$(bashio::config 'auth_user')
export AUTH_PASS=$(bashio::config 'auth_pass')
export OIDC_ENABLED=$(bashio::config 'oidc_enabled')
export OIDC_ISSUER=$(bashio::config 'oidc_issuer')
export OIDC_CLIENT_ID=$(bashio::config 'oidc_client_id')
export OIDC_CLIENT_SECRET=$(bashio::config 'oidc_client_secret')
export DISABLE_LOCAL_LOGIN=$(bashio::config 'disable_local_login')

mkdir -p "${DATA_DIR}"

# Generar FLASK_SECRET al primer arranque y persistirlo (antes caía siempre
# en el default hardcodeado "dev-secret-key" del código porque nunca se
# exportaba) — necesario para que las cookies de sesión (login local y el
# state/nonce del login SSO) no sean forjables por cualquiera que lea el
# fuente público del add-on.
SESSION_SECRET_FILE="${DATA_DIR}/flask_secret"
if [ ! -f "${SESSION_SECRET_FILE}" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${SESSION_SECRET_FILE}"
    chmod 600 "${SESSION_SECRET_FILE}"
    bashio::log.info "FLASK_SECRET generado y guardado."
fi
export FLASK_SECRET=$(cat "${SESSION_SECRET_FILE}")

bashio::log.info "Starting Spotify Tracker on port 8765..."
exec python3 /app/app.py
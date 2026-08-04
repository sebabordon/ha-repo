#!/bin/bash
# Arranca Postgres embebido (dueño: uid 1000, el mismo que usa Authentik,
# porque `ak` hace `chown -R authentik:authentik /data` en cada arranque) y
# despues Authentik en modo "allinone" (server + worker en un solo proceso).
set -euo pipefail

OPTIONS_FILE="/data/options.json"
DATA_DIR="/data"
PGDATA="${DATA_DIR}/postgres"
SECRET_FILE="${DATA_DIR}/secret_key"
PG_PASS_FILE="${DATA_DIR}/postgres_password"
AK_UID=1000
AK_GID=1000

log() { printf '[authentik-addon] %s\n' "$*"; }
cfg() { jq -r ".$1 // empty" "$OPTIONS_FILE"; }

AUTHENTIK_HOST_CFG="$(cfg authentik_host)"
COOKIE_DOMAIN="$(cfg cookie_domain)"
BOOTSTRAP_EMAIL="$(cfg bootstrap_email)"
BOOTSTRAP_PASSWORD="$(cfg bootstrap_password)"
TRUSTED_PROXY_CIDRS="$(cfg trusted_proxy_cidrs)"
LOG_LEVEL="$(cfg log_level)"
ERROR_REPORTING="$(cfg error_reporting)"
SMTP_HOST="$(cfg smtp_host)"
SMTP_PORT="$(cfg smtp_port)"
SMTP_USERNAME="$(cfg smtp_username)"
SMTP_PASSWORD="$(cfg smtp_password)"
SMTP_USE_TLS="$(cfg smtp_use_tls)"
SMTP_FROM="$(cfg smtp_from)"

if [ -z "${AUTHENTIK_HOST_CFG}" ] || [ "${AUTHENTIK_HOST_CFG}" = "auth.example.com" ]; then
    log "ERROR: configurá 'authentik_host' (ej: auth.sbsoft.com.ar) en la configuración del add-on."
    exit 1
fi
if [ -z "${BOOTSTRAP_PASSWORD}" ]; then
    log "ERROR: configurá 'bootstrap_password' (contraseña inicial del usuario akadmin) en la configuración del add-on."
    exit 1
fi

mkdir -p "${PGDATA}" "${DATA_DIR}/media" "${DATA_DIR}/certs" /run/postgresql

PGBIN="$(find /usr/lib/postgresql -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)/bin"
export PATH="${PGBIN}:${PATH}"

as_ak() { setpriv --reuid="${AK_UID}" --regid="${AK_GID}" --init-groups -- "$@"; }

# ---- Secretos persistidos en /data (sobreviven reinicios/actualizaciones) ----
if [ ! -f "${SECRET_FILE}" ]; then
    head -c 60 /dev/urandom | base64 | tr -d '\n' > "${SECRET_FILE}"
    chmod 600 "${SECRET_FILE}"
    log "AUTHENTIK_SECRET_KEY generado."
fi
export AUTHENTIK_SECRET_KEY
AUTHENTIK_SECRET_KEY="$(cat "${SECRET_FILE}")"

if [ ! -f "${PG_PASS_FILE}" ]; then
    head -c 32 /dev/urandom | base64 | tr -d '\n' > "${PG_PASS_FILE}"
    chmod 600 "${PG_PASS_FILE}"
fi
PG_PASSWORD="$(cat "${PG_PASS_FILE}")"

# ---- PostgreSQL: cluster propio bajo /data/postgres, dueño uid 1000 ----
chown -R "${AK_UID}:${AK_GID}" "${PGDATA}"
chown "${AK_UID}:${AK_GID}" /run/postgresql

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
    log "Inicializando PostgreSQL en ${PGDATA}..."
    as_ak initdb -D "${PGDATA}" -U authentik --auth=trust --encoding=UTF8 >/dev/null
fi

# El log va DENTRO de PGDATA (no en /data directo): /data es de root, solo
# /data/postgres quedó con permisos para uid 1000 (ver chown de arriba).
as_ak pg_ctl -D "${PGDATA}" -l "${PGDATA}/postgres.log" \
    -o "-c listen_addresses=127.0.0.1 -c unix_socket_directories=/run/postgresql" \
    -w start

pg_stop() {
    log "Deteniendo PostgreSQL..."
    as_ak pg_ctl -D "${PGDATA}" -m fast stop >/dev/null 2>&1 || true
}

# Solo el add-on habla con este Postgres: bindeado a 127.0.0.1, sin puerto
# expuesto en config.yaml. `authentik` es superusuario del cluster (creado
# via `initdb -U authentik`), así que no hay grants que gestionar.
as_ak psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U authentik -d postgres \
    -c "ALTER ROLE authentik WITH PASSWORD '${PG_PASSWORD}';" >/dev/null

if ! as_ak psql -tA -h 127.0.0.1 -U authentik -d postgres \
    -c "SELECT 1 FROM pg_database WHERE datname='authentik'" | grep -q 1; then
    as_ak createdb -h 127.0.0.1 -U authentik authentik
fi

export AUTHENTIK_POSTGRESQL__HOST=127.0.0.1
export AUTHENTIK_POSTGRESQL__PORT=5432
export AUTHENTIK_POSTGRESQL__NAME=authentik
export AUTHENTIK_POSTGRESQL__USER=authentik
export AUTHENTIK_POSTGRESQL__PASSWORD="${PG_PASSWORD}"

export AUTHENTIK_LOG_LEVEL="${LOG_LEVEL}"
export AUTHENTIK_ERROR_REPORTING__ENABLED="${ERROR_REPORTING}"
export AUTHENTIK_DISABLE_UPDATE_CHECK=true
export AUTHENTIK_BOOTSTRAP_EMAIL="${BOOTSTRAP_EMAIL}"
export AUTHENTIK_BOOTSTRAP_PASSWORD="${BOOTSTRAP_PASSWORD}"
[ -n "${TRUSTED_PROXY_CIDRS}" ] && export AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS="${TRUSTED_PROXY_CIDRS}"
[ -n "${COOKIE_DOMAIN}" ] && export AUTHENTIK_COOKIE_DOMAIN="${COOKIE_DOMAIN}"

if [ -n "${SMTP_HOST}" ]; then
    export AUTHENTIK_EMAIL__HOST="${SMTP_HOST}"
    export AUTHENTIK_EMAIL__PORT="${SMTP_PORT:-587}"
    export AUTHENTIK_EMAIL__USERNAME="${SMTP_USERNAME}"
    export AUTHENTIK_EMAIL__PASSWORD="${SMTP_PASSWORD}"
    export AUTHENTIK_EMAIL__USE_TLS="${SMTP_USE_TLS}"
    export AUTHENTIK_EMAIL__FROM="${SMTP_FROM:-authentik@${AUTHENTIK_HOST_CFG}}"
fi

shutdown_handler() {
    trap - TERM INT
    log "Señal de apagado recibida..."
    if [ -n "${AK_PID:-}" ]; then
        kill -TERM "${AK_PID}" 2>/dev/null || true
        wait "${AK_PID}" 2>/dev/null || true
    fi
    pg_stop
    exit 0
}
trap shutdown_handler TERM INT

log "Iniciando Authentik (modo allinone) para https://${AUTHENTIK_HOST_CFG} ..."
ak allinone &
AK_PID=$!
wait "${AK_PID}"
pg_stop

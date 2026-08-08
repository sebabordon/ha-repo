#!/bin/sh
# Traduce las opciones del add-on (options.json) a las env vars que espera el
# binario /rac (mismo mecanismo que cualquier outpost manual de Authentik:
# AUTHENTIK_HOST + AUTHENTIK_TOKEN, ver
# https://docs.goauthentik.io/add-secure-apps/outposts/manual-deploy-docker-compose/).
# sh en vez de bash: la imagen base (ghcr.io/goauthentik/rac, basada en guacd)
# no tiene garantizado bash.
set -eu

OPTIONS_FILE="/data/options.json"

log() { printf '[authentik-rac-addon] %s\n' "$*"; }
# NO usar `.campo // empty`: en jq `//` trata `false` como "vacío" igual que
# null (mismo bug que ya nos mordió en el add-on principal con error_reporting).
cfg() { jq -r --arg k "$1" '.[$k] as $v | if $v == null then "" else $v end' "$OPTIONS_FILE"; }

AUTHENTIK_HOST_CFG="$(cfg authentik_host)"
AUTHENTIK_TOKEN_CFG="$(cfg authentik_token)"
AUTHENTIK_INSECURE_CFG="$(cfg authentik_insecure)"

if [ -z "${AUTHENTIK_HOST_CFG}" ] || [ "${AUTHENTIK_HOST_CFG}" = "https://auth.example.com" ]; then
    log "ERROR: configurá 'authentik_host' (ej: https://auth.sbsoft.com.ar) en la configuración del add-on."
    exit 1
fi
if [ -z "${AUTHENTIK_TOKEN_CFG}" ]; then
    log "ERROR: configurá 'authentik_token' — el token que Authentik generó al crear el outpost RAC"
    log "       (Admin interface → Outposts → tu outpost RAC → 'View Deployment Info' / 'Download Token')."
    exit 1
fi

export AUTHENTIK_HOST="${AUTHENTIK_HOST_CFG}"
export AUTHENTIK_TOKEN="${AUTHENTIK_TOKEN_CFG}"
export AUTHENTIK_INSECURE="${AUTHENTIK_INSECURE_CFG}"

log "Conectando outpost RAC a ${AUTHENTIK_HOST_CFG} ..."
# run.sh corre como root (necesario para leer /data/options.json — ver
# Dockerfile); acá recién bajamos privilegios al uid no-root de la imagen
# base para el proceso real. setpriv es de util-linux, paquete esencial de
# Debian, siempre presente.
exec setpriv --reuid=1000 --regid=1000 --init-groups -- /rac

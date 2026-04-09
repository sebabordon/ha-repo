#!/usr/bin/with-contenv bashio

export SPOTIFY_CLIENT_ID=$(bashio::config 'spotify_client_id')
export SPOTIFY_CLIENT_SECRET=$(bashio::config 'spotify_client_secret')
export SCAN_DAY=$(bashio::config 'scan_day')
export SCAN_HOUR=$(bashio::config 'scan_hour')
export DATA_DIR="/data"
export INGRESS_ENTRY=$(bashio::addon.ingress_entry)

mkdir -p "${DATA_DIR}"

nginx

bashio::log.info "Starting Spotify Tracker..."
exec python3 /app/app.py
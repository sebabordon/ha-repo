#!/usr/bin/with-contenv bashio

export SPOTIFY_CLIENT_ID=$(bashio::config 'spotify_client_id')
export SPOTIFY_CLIENT_SECRET=$(bashio::config 'spotify_client_secret')
export REDIRECT_URI=$(bashio::config 'redirect_uri')
export SCAN_DAY=$(bashio::config 'scan_day')
export SCAN_HOUR=$(bashio::config 'scan_hour')
export DATA_DIR="/data"
export AUTH_USER=$(bashio::config 'auth_user')
export AUTH_PASS=$(bashio::config 'auth_pass')

mkdir -p "${DATA_DIR}"

bashio::log.info "Starting Spotify Tracker on port 8765..."
exec python3 /app/app.py
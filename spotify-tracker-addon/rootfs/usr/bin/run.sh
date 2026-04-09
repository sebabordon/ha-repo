#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Spotify Liked Songs Tracker..."

# Read options
export SPOTIFY_CLIENT_ID=$(bashio::config 'spotify_client_id')
export SPOTIFY_CLIENT_SECRET=$(bashio::config 'spotify_client_secret')
export SCAN_DAY=$(bashio::config 'scan_day')
export SCAN_HOUR=$(bashio::config 'scan_hour')
export DATA_DIR="/data"
export FLASK_SECRET=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "spotify-tracker-secret")

# HA ingress path
export INGRESS_ENTRY=$(bashio::addon.ingress_entry)

mkdir -p "$DATA_DIR"

# Start nginx
nginx &

# Start Flask app using venv
bashio::log.info "Starting web app on port 5000..."
/opt/venv/bin/python3 /app/app.py

#!/usr/bin/with-contenv bashio

DECO_HOST=$(bashio::config 'deco_host')
DECO_PASS=$(bashio::config 'deco_pass')
AGH_HOST=$(bashio::config 'agh_host')
AGH_USER=$(bashio::config 'agh_user')
AGH_PASS=$(bashio::config 'agh_pass')
MIN_IP=$(bashio::config 'min_ip_suffix')
RUN_ON_START=$(bashio::config 'run_on_start')
STALE_DAYS=$(bashio::config 'stale_days')
EXCLUDE_RANDOM_MAC=$(bashio::config 'exclude_random_mac')
NETWORK_CIDR=$(bashio::config 'network_cidr')
# bashio::config imprime los valores de una lista uno por linea (no JSON), asi
# que para pasarle un array real al script leemos /data/options.json directo.
PARENTAL_EXEMPT_JSON=$(jq -c '.parental_exempt // []' /data/options.json)
UNFILTERED_JSON=$(jq -c '.unfiltered_devices // []' /data/options.json)

run_sync() {
    bashio::log.info "Iniciando sincronizacion Deco -> AdGuard Home..."
    EXTRA_ARGS=()
    if ! bashio::var.true "$EXCLUDE_RANDOM_MAC"; then
        EXTRA_ARGS+=(--no-exclude-random-mac)
    fi
    python3 /app/deco_to_adguard.py \
        --deco-host  "$DECO_HOST" \
        --deco-pass  "$DECO_PASS" \
        --agh-host   "$AGH_HOST" \
        --agh-user   "$AGH_USER" \
        --agh-pass   "$AGH_PASS" \
        --min-ip     "$MIN_IP" \
        --stale-days "$STALE_DAYS" \
        --network    "$NETWORK_CIDR" \
        --parental-exempt-json "$PARENTAL_EXEMPT_JSON" \
        --unfiltered-json "$UNFILTERED_JSON" \
        --state-file /data/deco_adguard_state.json \
        --output     /tmp/clientes_adguard.yaml \
        "${EXTRA_ARGS[@]}"
    bashio::log.info "Sincronizacion completada."
}

# Correr al inicio si está habilitado
if bashio::var.true "$RUN_ON_START"; then
    run_sync
fi

# Loop: correr cada 6 horas
bashio::log.info "Programando sync cada 6 horas..."
while true; do
    sleep 21600
    run_sync
done

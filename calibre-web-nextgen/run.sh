#!/usr/bin/env bash
# Shim: opciones del add-on -> env, enlaza la biblioteca (/media/Libros) y el
# ingest, levanta nginx para Ingress y cede el control al /init de upstream.
set -eu

eval "$(python3 - <<'PY'
import json, shlex
try:
    o = json.load(open("/data/options.json"))
except Exception:
    o = {}
def sh(name, val):
    print("%s=%s" % (name, shlex.quote(str(val))))
sh("PUID", int(o.get("PUID", 0) or 0))
sh("PGID", int(o.get("PGID", 0) or 0))
tz = str(o.get("TZ") or "").strip()
if tz and all(c.isalnum() or c in "/_+-" for c in tz):
    sh("TZ", tz)
sh("_LIBRARY", str(o.get("library") or "").strip())
sh("_INGEST", str(o.get("ingest") or "").strip())
sh("_TRUSTED_ORIGINS", str(o.get("trusted_origins") or "").strip())
sh("_PROXY_COUNT", int(o.get("trusted_proxy_count", 1) or 1))
PY
)"
export PUID PGID
[ -n "${TZ:-}" ] && export TZ || true
echo "[cwng] PUID=${PUID} PGID=${PGID} TZ=${TZ:-<system>}"

# /calibre-library y /cwa-book-ingest son VOLUMEs de la imagen (no se pueden
# reemplazar por symlinks); upstream soporta estas variables como ruta
# autoritativa de la biblioteca y del ingest.
if [ -n "${_LIBRARY}" ]; then
    if [ -d "${_LIBRARY}" ]; then
        export CWA_CALIBRE_LIBRARY_DIR="${_LIBRARY}"
        echo "[cwng] library: ${_LIBRARY}"
        [ -f "${_LIBRARY}/metadata.db" ] && echo "[cwng] library: metadata.db encontrado" || echo "[cwng] library: sin metadata.db en la raíz (se busca en subcarpetas / se crea una nueva)"
    else
        echo "[cwng] WARN: library '${_LIBRARY}' no existe (¿está montado /media?)"
    fi
fi
if [ -n "${_INGEST}" ]; then
    if [ -d "${_INGEST}" ]; then
        export CWA_INGEST_FOLDER="${_INGEST}"
        echo "[cwng] ingest: ${_INGEST}"
    else
        echo "[cwng] WARN: ingest '${_INGEST}' no existe"
    fi
fi

# Reverse proxy externo (ej. Nginx Proxy Manager): sin esto el login falla con
# "Rejected cross-site POST" cuando el proxy reescribe el Host.
export TRUSTED_PROXY_COUNT="${_PROXY_COUNT}"
if [ -n "${_TRUSTED_ORIGINS}" ]; then
    export CWNG_TRUSTED_ORIGINS="${_TRUSTED_ORIGINS}"
    echo "[cwng] trusted origins: ${_TRUSTED_ORIGINS}"
fi

if command -v nginx >/dev/null 2>&1; then
    mkdir -p /var/lib/nginx /var/log/nginx
    if nginx -t -c /etc/nginx-ingress.conf 2>/tmp/nginx.err; then
        nginx -c /etc/nginx-ingress.conf
        echo "[cwng] Ingress en :8099 -> :8083"
    else
        sed 's/^/[cwng]   /' /tmp/nginx.err || true
    fi
fi

exec /init

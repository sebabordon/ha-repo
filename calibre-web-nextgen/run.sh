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
PY
)"
export PUID PGID
[ -n "${TZ:-}" ] && export TZ || true
echo "[cwng] PUID=${PUID} PGID=${PGID} TZ=${TZ:-<system>}"

# CWA/NextGen solo mira /calibre-library: lo apuntamos a la carpeta elegida
# con un symlink (no hace falta mount ni privilegios).
link_dir() {
    local label="$1" src="$2" dst="$3"
    if [ -z "$src" ]; then return 0; fi
    if [ ! -d "$src" ]; then
        echo "[cwng] WARN: $label '$src' no existe (¿está montado /media?)"
        return 0
    fi
    if [ -L "$dst" ]; then rm -f "$dst"
    elif [ -d "$dst" ]; then
        # La imagen trae el directorio con contenido por defecto (efímero, vive
        # en el filesystem del contenedor): se aparta en vez de borrarlo.
        if mountpoint -q "$dst"; then echo "[cwng] WARN: $dst es un mountpoint, no se enlaza $label"; return 0; fi
        rm -rf "${dst}.default"
        mv "$dst" "${dst}.default" || { echo "[cwng] WARN: no se pudo apartar $dst, no se enlaza $label"; return 0; }
    fi
    ln -s "$src" "$dst"
    echo "[cwng] $label: $src -> $dst"
}
link_dir library "${_LIBRARY}" /calibre-library
link_dir ingest "${_INGEST}" /cwa-book-ingest
[ -f /calibre-library/metadata.db ] && echo "[cwng] library: metadata.db encontrado" || true

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

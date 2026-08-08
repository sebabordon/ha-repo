# Mismo versionado que el add-on "authentik" principal — server y outposts
# deben ir en la misma versión para evitar incompatibilidades de API/websocket.
ARG AUTHENTIK_VERSION=2026.5.6
FROM ghcr.io/goauthentik/rac:${AUTHENTIK_VERSION}

USER root

# Solo hace falta jq para leer /data/options.json que nos escribe el Supervisor.
# El binario /rac y guacd ya vienen en la imagen base.
RUN apt-get update && apt-get install -y --no-install-recommends \
        jq \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

# OJO: no bajar a USER 1000 acá. run.sh necesita leer /data/options.json
# (lo escribe el Supervisor como root, con permisos que uid 1000 no puede
# abrir — "Permission denied" con jq). run.sh se queda como root para leer
# la config y recién al final baja privilegios (setpriv) para ejecutar /rac.

ENTRYPOINT []
CMD ["/run.sh"]

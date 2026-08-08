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

# El outpost es un cliente saliente sin estado: no necesita root ni /data
# persistente, corre con el mismo uid no-root que trae la imagen base.
USER 1000

ENTRYPOINT []
CMD ["/run.sh"]

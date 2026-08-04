# Pinned a la versión "actual" del compose.yml oficial (docs.goauthentik.io/compose.yml)
# al momento de crear este add-on. A partir de 2025.10 Authentik dejó de depender
# de Redis (caché, tasks, websockets y el outpost embebido corren sobre Postgres),
# así que este add-on solo bundlea Postgres + Authentik (server+worker en un solo
# proceso, modo "allinone").
ARG AUTHENTIK_VERSION=2026.5.6
FROM ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}

USER root

# La imagen base ya trae `authentik` (uid 1000) y setpriv (util-linux es un
# paquete esencial de Debian, siempre presente). Solo hace falta Postgres y jq
# (para leer /data/options.json que nos escribe el Supervisor).
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql \
        jq \
    && rm -rf /var/lib/apt/lists/*

# La imagen base crea /media como directorio real y /data/media como symlink
# hacia él (al revés de lo que necesitamos para persistir en /data). Hay que
# borrar también el symlink viejo /data/media antes del mkdir: si no, mkdir -p
# se choca con ese symlink (ahora roto, porque ya borramos /media) y falla.
RUN rm -rf /media /certs /data/media /data/certs \
    && mkdir -p /data/media /data/certs \
    && ln -s /data/media /media \
    && ln -s /data/certs /certs

# Evita que Authentik use /dev/shm (shm_size default de Docker = 64MB, y HA
# Supervisor no permite configurar shm_size por add-on). /tmp vive en el
# filesystem normal del contenedor, sin ese límite artificial.
ENV TMPDIR=/tmp

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT []
CMD ["/run.sh"]

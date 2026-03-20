ARG BUILD_FROM
FROM debian:bookworm-slim

ENV LANG=C.UTF-8
ENV CUPS_DATADIR=/data/cups
ENV CUPS_CACHEDIR=/data/cups/cache
ENV CUPS_LOGDIR=/data/cups/logs
ENV CUPS_STATEDIR=/data/cups/state
ENV CUPS_SERVERROOT=/data/cups/config
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        cups \
        cups-filters \
        ghostscript \
        libcups2 \
        libcupsimage2 \
        curl \
        patchelf \
        dpkg \
        && \
    # Habilitar multiarch para armhf
    dpkg --add-architecture armhf && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libc6:armhf \
        libstdc++6:armhf \
        libcups2:armhf \
        libcupsimage2:armhf \
    && \
    rm -rf /var/lib/apt/lists/*

COPY rootfs /

RUN find /etc/cont-init.d/ -type f -exec chmod a+x {} \; && \
    chmod a+x /usr/lib/cups/filter/rastertospl && \
    chmod a+x /usr/lib/cups/filter/pstosecps && \
    patchelf --set-interpreter /lib/ld-linux-armhf.so.3 /usr/lib/cups/filter/rastertospl && \
    patchelf --set-interpreter /lib/ld-linux-armhf.so.3 /usr/lib/cups/filter/pstosecps

EXPOSE 631

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:631/ || exit 1

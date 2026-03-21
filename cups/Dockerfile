ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8
ENV CUPS_DATADIR=/data/cups
ENV CUPS_CACHEDIR=/data/cups/cache
ENV CUPS_LOGDIR=/data/cups/logs
ENV CUPS_STATEDIR=/data/cups/state
ENV CUPS_SERVERROOT=/data/cups/config

RUN \
    echo "http://dl-cdn.alpinelinux.org/alpine/v$(cat /etc/alpine-release | cut -d'.' -f1,2)/main" > /etc/apk/repositories && \
    echo "http://dl-cdn.alpinelinux.org/alpine/v$(cat /etc/alpine-release | cut -d'.' -f1,2)/community" >> /etc/apk/repositories && \
    apk update && \
    apk add --no-cache \
        cups \
        cups-filters \
        ghostscript \
        libjpeg-turbo \
        net-snmp \
        curl \
        qemu-arm \
        patchelf \
        epson-inkjet-printer-escpr

COPY rootfs /

RUN chmod 755 /etc/cont-init.d/cups.sh && \
    chmod 755 /usr/lib/cups/filter/rastertospl && \
    chmod 755 /usr/lib/cups/filter/pstosecps && \
    patchelf --set-interpreter /usr/bin/qemu-arm /usr/lib/cups/filter/rastertospl && \
    patchelf --set-interpreter /usr/bin/qemu-arm /usr/lib/cups/filter/pstosecps

EXPOSE 631

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:631/ || exit 1

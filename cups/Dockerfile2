ARG BUILD_FROM
FROM $BUILD_FROM
# Add env
ENV LANG=C.UTF-8
# Set CUPS environment variables for data persistence
ENV CUPS_DATADIR=/data/cups
ENV CUPS_CACHEDIR=/data/cups/cache
ENV CUPS_LOGDIR=/data/cups/logs
ENV CUPS_STATEDIR=/data/cups/state
ENV CUPS_SERVERROOT=/data/cups/config
# Setup base
# Dependencias para compilar SpliX
RUN apk add --no-cache \
        cups \
        cups-filters \
        ghostscript \
        libjpeg-turbo \
        net-snmp \
        patchelf \
        libstdc++ \
        curl \
        epson-inkjet-printer-escpr 

# Copy data
COPY rootfs /
RUN chmod a+x /etc/cont-init.d/cups.sh && \
    chmod a+x /usr/lib/cups/filter/rastertospl && \
    chmod a+x /usr/lib/cups/filter/pstosecps && \
    patchelf --set-interpreter /lib/ld-linux-armhf.so.3 /usr/lib/cups/filter/rastertospl && \
    patchelf --set-interpreter /lib/ld-linux-armhf.so.3 /usr/lib/cups/filter/pstosecps

EXPOSE 631
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:631/ || exit 1

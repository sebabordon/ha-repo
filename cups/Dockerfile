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
        curl \
        git \
        make \
        g++ \
        cups-dev \
        ghostscript-dev \
        epson-inkjet-printer-escpr

# Compilar SpliX desde el branch xerox-3020
RUN git clone --branch xerox-3020 https://github.com/OpenPrinting/splix.git /tmp/splix \
    && cd /tmp/splix \
    && make \
    && make install \
    && rm -rf /tmp/splix
# Copy data
COPY rootfs /
RUN chmod a+x /etc/cont-init.d/cups.sh
# Expose CUPS web interface port
EXPOSE 631
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:631/ || exit 1

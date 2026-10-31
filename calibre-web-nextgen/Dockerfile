# Wrapper fino sobre la imagen multi-arch oficial de Calibre-Web-NextGen.
# El tag se mantiene 1:1 con `version:` de config.yaml.
ARG BUILD_FROM="ghcr.io/new-usemame/calibre-web-nextgen:v4.1.60"
FROM ${BUILD_FROM}

# nginx: traduce X-Ingress-Path de HA a X-Script-Name / X-Forwarded-Prefix.
# tzdata: para la opción TZ.
RUN \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get update \
        && apt-get install -y --no-install-recommends nginx-light tzdata \
        && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache nginx tzdata; \
    fi

COPY nginx-ingress.conf /etc/nginx-ingress.conf
COPY run.sh /ha-run.sh
RUN chmod a+x /ha-run.sh

ENTRYPOINT ["/ha-run.sh"]
CMD []

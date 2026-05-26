ARG BUILD_FROM
FROM $BUILD_FROM

# ── Dependencias del sistema ──────────────────────────────────────────────────
# python3 + pip para la app Flask/FastAPI
# chromium + librerías gráficas para Playwright (sin descargar binario propio)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    dbus \
    eudev \
    udev

# Playwright usará el Chromium del sistema en lugar de descargar el suyo
# (ahorra ~400 MB y evita problemas de libs en Alpine aarch64)
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

COPY requirements.txt .
# Paso 1: dependencias del proyecto desde el índice de HA (wheels pre-compilados para musl/aarch64)
RUN pip3 install --break-system-packages -r requirements.txt

# Paso 2: playwright y apscheduler no están en el índice de HA.
# PIP_CONFIG_FILE=/dev/null ignora el pip.conf del sistema (que incluye el índice de HA
# como extra-index-url y puede devolver respuestas vacías para playwright, confundiendo
# a pip con "from versions: none"). Con /dev/null de config, solo se usa PyPI puro.
RUN PIP_CONFIG_FILE=/dev/null pip3 install --break-system-packages \
    --index-url https://pypi.org/simple \
    "playwright>=1.44.0,<2.0" \
    "apscheduler>=3.10,<4"

COPY rootfs/app/ .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

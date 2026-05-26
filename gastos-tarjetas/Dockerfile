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
RUN pip3 install --break-system-packages -r requirements.txt

COPY rootfs/app/ .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

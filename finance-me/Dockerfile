ARG BUILD_FROM
FROM $BUILD_FROM

# ── Dependencias del sistema ──────────────────────────────────────────────────
# chromium-chromedriver: binario de ChromeDriver para Selenium (mismo paquete que chromium)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    dbus \
    eudev \
    udev

# Rutas de los binarios del sistema para Selenium
ENV CHROMIUM_BIN=/usr/bin/chromium-browser
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .
# selenium y apscheduler son pure Python (py3-none-any) → no hay problema de musl vs glibc
RUN pip3 install --break-system-packages -r requirements.txt

COPY rootfs/app/ .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

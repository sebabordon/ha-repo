ARG BUILD_FROM
FROM $BUILD_FROM

# ── Dependencias del sistema ──────────────────────────────────────────────────
# Google Chrome REAL (no Chromium open-source) — Akamai (AMEX/BBVA) rechaza el
# fingerprint del Chromium de Alpine (build open-source, sin códecs propietarios,
# render por software) aunque el login sea manual. Chrome pasa porque es el
# mismo binario que corre en una PC/Mac real.
#
# Google recién liberó builds arm64 de Chrome (jul 2026), pero todavía no hay
# chromedriver arm64 oficial de Google (Chrome for Testing solo publica linux64
# x86). Usamos el chromedriver que empaqueta Debian (`chromium-driver`), que
# para trixie está en ~v150 — un solo major de diferencia contra el Chrome
# ~v151 recién liberado, dentro de lo que Selenium tolera.
#
# La base cambia de Alpine (apk) a la Debian oficial de HA (con bashio/s6
# intactos) porque el .deb de Chrome no instala en Alpine (musl, no apt/dpkg).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    chromium-driver \
    ca-certificates \
    fonts-freefont-ttf \
    curl \
 && ARCH="$(dpkg --print-architecture)" \
 && curl -fsSL -o /tmp/chrome.deb \
    "https://dl.google.com/linux/direct/google-chrome-stable_current_${ARCH}.deb" \
 && apt-get install -y --no-install-recommends /tmp/chrome.deb \
 && rm -f /tmp/chrome.deb \
 && rm -rf /var/lib/apt/lists/*

# Rutas de los binarios del sistema para Selenium
ENV CHROMIUM_BIN=/usr/bin/google-chrome-stable
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY rootfs/app/ .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

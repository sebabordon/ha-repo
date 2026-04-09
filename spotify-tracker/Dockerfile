FROM ghcr.io/home-assistant/aarch64-base:latest

RUN apk add --no-cache python3 py3-pip py3-virtualenv nginx

COPY requirements.txt /tmp/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY rootfs /

RUN chmod +x /usr/bin/run.sh

CMD ["/usr/bin/run.sh"]

ARG BUILD_FROM
FROM $BUILD_FROM

# Install nginx
RUN apk add --no-cache nginx

# Copy requirements and install into venv
COPY requirements.txt /tmp/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Copy app files
COPY rootfs /

# Make run script executable
RUN chmod +x /usr/bin/run.sh

CMD ["/usr/bin/run.sh"]

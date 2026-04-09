ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python, pip, nginx
RUN apk add --no-cache python3 py3-pip nginx

# Copy requirements and install
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy app files
COPY rootfs /

# Make run script executable
RUN chmod +x /usr/bin/run.sh

CMD ["/usr/bin/run.sh"]

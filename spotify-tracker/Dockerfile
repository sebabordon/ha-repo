ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip nginx

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY rootfs/app/ .
COPY rootfs/etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf

COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

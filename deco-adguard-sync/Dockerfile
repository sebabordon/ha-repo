ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY deco_to_adguard.py .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

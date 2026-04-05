FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ARG MEDIAMTX_VERSION=1.15.4
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fSL "https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}/mediamtx_v${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz" | \
    tar xz -C /usr/local/bin/ mediamtx

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MEDIA_DIR=/media \
    MEDIAMTX_PATH=/usr/local/bin/mediamtx \
    WEB_PORT=10090

EXPOSE 10090 8554 8888 9997

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10090"]

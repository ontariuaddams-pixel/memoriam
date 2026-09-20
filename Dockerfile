FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    ca-certificates \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/vault/public_stream && chmod -R 777 /app/vault

EXPOSE 7860

CMD ["python", "unit_es720_ghost_carrier.py"]

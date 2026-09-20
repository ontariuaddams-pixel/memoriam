FROM python:3.10-slim

# Install system dependencies, audio tools, H264 libraries, and standard fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    fonts-dejavu-core \
    fontconfig \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ensure standard system font configs are refreshed
RUN fc-cache -f -v

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Explicitly create and permit vault access
RUN mkdir -p vault/public_stream && chmod -R 777 vault

EXPOSE 7860

CMD ["python", "unit_es720_ghost_carrier.py"]

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir --default-timeout=180 -r /tmp/worker-requirements.txt
COPY api/app /app/app
COPY worker /app/worker

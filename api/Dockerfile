FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY api/app /app/app
COPY worker /app/worker
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

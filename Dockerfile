FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY anvaya_api ./anvaya_api

# ANVAYA_DATA_DIR defaults to /data (config.py); the ingest/knowledge store lives here.
RUN mkdir -p /data

EXPOSE 8300

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=60s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8300/healthz', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "anvaya_api.main:app", "--host", "0.0.0.0", "--port", "8300"]

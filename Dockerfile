# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System libs for crypto/Pillow build and wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libjpeg62-turbo-dev zlib1g-dev curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUS_DEV=0 \
    BUS_DB=/data/app.db

# Non-root runtime user
RUN useradd -m appuser
WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Data directory for SQLite persistence
RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8765
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD curl -fsS http://127.0.0.1:8765/health >/dev/null || exit 1
# FastAPI app object exposed by core.api.http
CMD ["python", "-m", "uvicorn", "core.api.http:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765"]

# WIRE API + workers — one image, two commands.
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY services/api/pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY services/api/ ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# API:     docker run image
# Worker:  docker run image celery -A wire_api.worker.celery_app worker --beat ...
CMD ["uvicorn", "wire_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

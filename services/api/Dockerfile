# WIRE backend — Hugging Face Spaces (Docker) / any container host.
# Lite mode: SQLite + embedded worker, one container, zero extra services.
# HF Spaces expects the app on port 7860.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -r pyproject.toml

COPY . .

# writable data dir (mount a persistent volume here on HF to keep history)
ENV WIRE_DB_DIR=/data
RUN mkdir -p /data && chmod 777 /data
ENV DATABASE_URL=sqlite+aiosqlite:////data/wire.db
ENV EMBEDDED_WORKER=1
ENV PYTHONUNBUFFERED=1

EXPOSE 7860
CMD ["sh", "-c", "alembic upgrade head && python -m wire_api.seed && uvicorn wire_api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]

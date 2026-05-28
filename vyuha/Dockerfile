FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (layer-cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x /app/start.sh

# SERVICE_TYPE=worker → Celery; default → uvicorn API
CMD ["/app/start.sh"]

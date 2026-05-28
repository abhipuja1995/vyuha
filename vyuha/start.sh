#!/bin/sh
# Unified entry point — SERVICE_TYPE env var selects what to run.
# API (default): runs migrations then uvicorn
# worker: Celery worker

if [ "$SERVICE_TYPE" = "worker" ]; then
    exec celery -A vyuha.workers.celery_app worker \
        --loglevel=info \
        --concurrency=4
else
    echo "Running database migrations..."
    alembic upgrade head
    echo "Starting API server..."
    exec uvicorn vyuha.orchestrator.main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}"
fi

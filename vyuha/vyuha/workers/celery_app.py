from __future__ import annotations

from celery import Celery

from vyuha.config import settings

app = Celery(
    "vyuha",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["vyuha.workers.tasks"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,        # one task at a time per worker process
    task_acks_late=True,                 # ack after completion, not on pickup
    task_reject_on_worker_lost=True,
    result_expires=86400,                # 24h result retention
    task_soft_time_limit=300,            # 5 min soft limit per test run
    task_time_limit=600,                 # 10 min hard limit
)

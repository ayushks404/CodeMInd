"""
celery_app.py — Celery initialization for CodeMind AI workers

Celery uses Redis as both:
- Broker: where tasks are sent (the queue)
- Backend: where results are stored

Queues:
- query_jobs → HIGH priority — user waiting for answer
- index_jobs → LOW  priority — background indexing
"""

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "codemind",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "workers.query_worker",
        "workers.index_worker",
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Each task goes to its own queue
    task_routes={
        "workers.query_worker.run_query": {"queue": "query_jobs"},
        "workers.index_worker.run_index": {"queue": "index_jobs"},
    },

    # Only ack after task completes — prevents lost jobs
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,

    # Keep results for 1 hour
    result_expires=3600,

    # FIX: was 4 — with --concurrency=1 per worker container this caused each worker
    # to pre-fetch 4 jobs and hold them, starving the other 2 worker containers entirely.
    # Set to 1 so each worker only pulls what it can actually run right now.
    worker_prefetch_multiplier=1,
)

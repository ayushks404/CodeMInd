"""
index_worker.py — Celery worker for indexing GitHub repositories

Flow:
1. Node.js project_controllers.js puts job in Redis queue
2. This worker picks it up
3. Runs the existing index_repo pipeline from rag_engine.py
4. Publishes result to Redis pub/sub
5. WebSocket service picks it up and pushes to frontend
"""

import logging
import re
from celery_app import celery_app
from rag.rag_engine import index_repo
from notifications.redis_publisher import publish_indexing_complete, publish_job_failed

logging.basicConfig(level=logging.INFO)


def validate_project_id(project_id: str) -> bool:
    """Only allow MongoDB ObjectId or UUID format."""
    return bool(re.match(
        r'^[a-f0-9]{24}$|^[a-f0-9\-]{36}$',
        project_id
    ))


def validate_github_url(url: str) -> bool:
    """Only allow public GitHub URLs."""
    pattern = r'^https://github\.com/[\w\-]+/[\w\-\.]+/?$'
    return bool(re.match(pattern, url))


@celery_app.task(
    name="workers.index_worker.run_index",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def run_index(self, job_id: str, project_id: str, user_id: str, repo_url: str):
    """
    Celery task — clones repo and indexes it into Qdrant.

    Args:
        job_id:     UUID — used to notify frontend when done
        project_id: project this repo belongs to
        user_id:    who to notify via WebSocket when done
        repo_url:   GitHub URL to clone and index
    """
    logging.info(f"[index_worker] Starting job {job_id} for project {project_id}")

    # Validate inputs before doing any work
    if not validate_project_id(project_id):
        publish_job_failed(
            user_id=user_id,
            job_id=job_id,
            reason="Invalid project_id format.",
            retryable=False,
        )
        return {"status": "failed", "job_id": job_id}

    if not validate_github_url(repo_url):
        publish_job_failed(
            user_id=user_id,
            job_id=job_id,
            reason="Invalid GitHub URL format.",
            retryable=False,
        )
        return {"status": "failed", "job_id": job_id}

    try:
        # index_repo already exists in rag/rag_engine.py
        # It clones, chunks, embeds, and saves to Qdrant
        result = index_repo(project_id, repo_url)

        file_count  = result.get("file_count", 0)
        chunk_count = result.get("chunk_count", 0)

        # Notify frontend — indexing done
        publish_indexing_complete(
            user_id=user_id,
            project_id=project_id,
            file_count=file_count,
            chunk_count=chunk_count,
        )

        logging.info(
            f"[index_worker] Job {job_id} completed — "
            f"{file_count} files, {chunk_count} chunks"
        )
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        logging.error(f"[index_worker] Job {job_id} failed: {exc}")

        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            publish_job_failed(
                user_id=user_id,
                job_id=job_id,
                reason=str(exc),
                retryable=True,
            )
            return {"status": "failed", "job_id": job_id}
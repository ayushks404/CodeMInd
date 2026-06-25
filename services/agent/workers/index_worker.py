"""
index_worker.py — Celery worker for indexing GitHub repositories

Flow:
1. Node.js project_controllers.js puts job in Redis queue
2. This worker picks it up
3. Runs the existing index_repo pipeline from rag_engine.py
4. Calls PATCH /api/project/:id/indexed on the project service
   so MongoDB sets indexed=true (fixes the "Indexing..." forever bug)
5. Publishes result to Redis pub/sub
6. WebSocket service picks it up and pushes to frontend
"""

import logging
import os
import re
import requests
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
        result = index_repo(project_id, repo_url)

        # FIX: rag_engine.index_repo returns "files" and "chunks" but the worker
        # was reading "file_count" and "chunk_count" — they never matched, so
        # fileCount and chunkCount were always 0 in the callback.
        file_count  = result.get("files",  0)
        chunk_count = result.get("chunks", 0)

        # FIX: call PATCH /api/project/:id/indexed so MongoDB sets indexed=true.
        # Without this, the dashboard showed "Indexing..." forever because nothing
        # in the system was ever flipping that flag after indexing completed.
        project_service_url = os.environ.get("PROJECT_SERVICE_URL", "http://project:5002")
        internal_secret     = os.environ.get("INTERNAL_SECRET", "")
        try:
            resp = requests.patch(
                f"{project_service_url}/api/project/{project_id}/indexed",
                json={"fileCount": file_count, "chunkCount": chunk_count},
                headers={"x-internal-secret": internal_secret},
                timeout=10,
            )
            resp.raise_for_status()
            logging.info(f"[index_worker] Marked project {project_id} as indexed in DB")
        except Exception as cb_err:
            # Non-fatal — indexing succeeded; only the DB flag update failed.
            # Log prominently so it's easy to spot in the worker logs.
            logging.error(
                f"[index_worker] WARN: failed to mark project {project_id} indexed: {cb_err}"
            )

        # Notify frontend via Redis pub/sub — WebSocket service forwards to browser
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
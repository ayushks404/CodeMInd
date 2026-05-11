"""
publisher.py — Redis pub/sub publisher

After Celery worker finishes a job, it calls publish_result().
Publishes to channel ws:notify:{user_id}.
WebSocket service subscribes and pushes to browser.
"""

import os
import json
import redis
import logging

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_redis_client = None

def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def publish_query_complete(user_id: str, job_id: str, answer: str,
                           confidence: float, sources: list, trace: list):
    channel = f"ws:notify:{user_id}"
    message = json.dumps({
        "event":      "query_complete",
        "job_id":     job_id,
        "answer":     answer,
        "confidence": confidence,
        "sources":    sources,
        "trace":      trace,
    })
    try:
        get_redis().publish(channel, message)
        logging.info(f"Published query_complete to {channel}")
    except Exception as e:
        logging.error(f"Redis publish failed: {e}")


def publish_indexing_complete(user_id: str, project_id: str,
                               file_count: int, chunk_count: int):
    channel = f"ws:notify:{user_id}"
    message = json.dumps({
        "event":       "indexing_complete",
        "project_id":  project_id,
        "file_count":  file_count,
        "chunk_count": chunk_count,
    })
    try:
        get_redis().publish(channel, message)
    except Exception as e:
        logging.error(f"Redis publish failed: {e}")


def publish_job_failed(user_id: str, job_id: str, reason: str, retryable: bool = True):
    channel = f"ws:notify:{user_id}"
    message = json.dumps({
        "event":     "job_failed",
        "job_id":    job_id,
        "reason":    reason,
        "retryable": retryable,
    })
    try:
        get_redis().publish(channel, message)
    except Exception as e:
        logging.error(f"Redis publish failed: {e}")
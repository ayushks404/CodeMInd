"""
redis_publisher.py — Redis pub/sub publisher

After Celery worker finishes a job, it calls publish_result().
Publishes to channel ws:notify:{user_id}.
WebSocket service subscribes and pushes to browser.

Events:
- query_complete    → answer ready hai
- indexing_complete → repo indexed ho gaya
- agent_step        → agent ne ek tool use kiya (Phase 3 new)
- job_failed        → kuch toot gaya
"""

import os
import json
import redis
import logging

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_redis_client = None

def get_redis():
     """Singleton Redis client — ek baar connect karo, baar baar use karo."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def publish_query_complete(user_id: str, job_id: str, answer: str,
                           confidence: float, sources: list, trace: list):
    """
    Query complete — answer ready hai.
    WebSocket service yeh receive karke browser ko push karega.
    """
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
        logging.info(f"[publisher] query_complete published for job  {job_id}")
    except Exception as e:
        logging.error(f"[publisher] Failed to publish query_complete: {e}")


def publish_indexing_complete(user_id: str, project_id: str,
                               file_count: int, chunk_count: int):
    """
    Indexing complete — repo indexed ho gaya.
    Frontend project status update karega.
    """
    channel = f"ws:notify:{user_id}"
    message = json.dumps({
        "event":       "indexing_complete",
        "project_id":  project_id,
        "file_count":  file_count,
        "chunk_count": chunk_count,
    })
    try:
        get_redis().publish(channel, json.dumps(payload))
        logger.info(f"[publisher] indexing_complete published for project {project_id}")
    except Exception as e:
        logger.error(f"[publisher] Failed to publish indexing_complete: {e}")



def publish_agent_step(
    user_id: str,
    job_id: str,
    step: str,
    tool_used: str,
):
    """
    Agent ne ek step complete kiya — tool use kiya.

    Phase 3 new event.
    Frontend pe live dikhega: "🔍 Searching code...", "📄 Reading file..."
    User ko pata chalta hai agent kya soch raha hai.

    Args:
        user_id:   kis user ko notify karna hai
        job_id:    kaun sa query job
        step:      human-readable description "Searching for authentication logic..."
        tool_used: tool ka naam "search_code", "read_file", etc.
    """
    channel = f"ws:notify:{user_id}"
    payload = {
        "event":     "agent_step",
        "job_id":    job_id,
        "step":      step,
        "tool_used": tool_used,
    }
    try:
        get_redis().publish(channel, json.dumps(payload))
        logger.debug(f"[publisher] agent_step published: {step}")
    except Exception as e:
        logger.error(f"[publisher] Failed to publish agent_step: {e}")


def publish_job_failed(user_id: str, job_id: str, reason: str, retryable: bool = True):
    
    """
    Job fail ho gaya — frontend ko batao.
    Retry button dikhana hai ya nahi yeh retryable flag se decide hoga.
    """
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
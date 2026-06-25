"""
query_worker.py — Celery worker for answering codebase questions

Flow:
1. Node.js pushQueryJob() → Redis "query_jobs" queue mein likhta hai
2. Yeh worker queue se task uthata hai
3. LangGraph ReAct graph run karo — agent tools use karta hai
4. Redis pub/sub mein result publish karta hai
5. WebSocket service browser ko push karta hai
"""

import logging
from celery_app import celery_app
from graph.react_graph import get_react_graph
from notifications.redis_publisher import publish_query_complete, publish_job_failed

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.query_worker.run_query",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_query(self, job_id: str, project_id: str, user_id: str, question: str):
    """
    Celery task — LangGraph ReAct agent chalao.

    Phase 2 se yahi function tha, lekin andar while loop tha.
    Ab andar graph.invoke() hai — poora agent yahan chal raha hai.
    """
    logger.info(f"[query_worker] Job {job_id} start | project={project_id} | user={user_id}")

    try:
        # Initial state banao
        initial_state = {
            "project_id":       project_id,
            "user_id":          user_id,
            "job_id":           job_id,
            "question":         question,
            "original_question": question,
            "query":            question,
            "tool_results":     [],
            "iterations":       0,
            "tool_calls_done":  0,
            "answer":           "",
            "confidence":       0.0,
            "sources":          [],
            "trace":            [],
            "should_continue":  False,
            "query_type":       "simple",
        }

        # LangGraph graph run karo
        # Yeh internally:
        # planner → tool_selector → tool_executor → observation
        # → answer_generator → critic → (retry ya end)
        graph = get_react_graph()
        final_state = graph.invoke(initial_state)

        answer     = final_state.get("answer", "No answer generated.")
        confidence = final_state.get("confidence", 0.0)
        sources    = final_state.get("sources", [])
        trace      = final_state.get("trace", [])

        logger.info(
            f"[query_worker] Job {job_id} completed | "
            f"confidence={confidence:.3f} | "
            f"iterations={final_state.get('iterations', 0)}"
        )

        # Result publish karo — WebSocket browser ko bhejega
        publish_query_complete(
            user_id=user_id,
            job_id=job_id,
            answer=answer,
            confidence=confidence,
            sources=sources,
            trace=trace,
        )

        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        logger.error(f"[query_worker] Job {job_id} failed: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            publish_job_failed(
                user_id=user_id,
                job_id=job_id,
                reason=str(exc),
                retryable=False,
            )
            return {"status": "failed", "job_id": job_id}

"""
query_worker.py — Celery worker for answering codebase questions

Flow:
1. Node.js pushQueryJob() → Redis "query_jobs" queue mein likhta hai
2. Yeh worker queue se task uthata hai
3. RAG pipeline + critic loop chalata hai
4. Redis pub/sub mein result publish karta hai
5. WebSocket service browser ko push karta hai
"""
"""
query_worker.py — Celery worker for answering codebase questions
"""

import logging
import numpy as np
from celery_app import celery_app
from rag.rag_engine import answer_question
from graph.critic import critic_agent
from notifications.redis_publisher import publish_query_complete, publish_job_failed

logging.basicConfig(level=logging.INFO)


def compute_confidence(query_vector, retrieved_vectors):
    if not retrieved_vectors:
        return 0.0
    q = query_vector[0]
    q_norm = q / (np.linalg.norm(q) + 1e-10)
    sims = []
    for v in retrieved_vectors:
        v_norm = v / (np.linalg.norm(v) + 1e-10)
        sims.append(float(np.dot(q_norm, v_norm)))
    return float(np.mean(sims))


@celery_app.task(
    name="workers.query_worker.run_query",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_query(self, job_id: str, project_id: str, user_id: str, question: str):
    logging.info(f"[query_worker] Job {job_id} start — user={user_id}")

    MAX_ITERATIONS = 3

    state = {
        "project_id":     project_id,
        "query":          question,
        "original_query": question,
        "iterations":     0,
        "answer":         None,
        "confidence":     0.0,
    }

    trace  = []
    result = {}

    try:
        while state["iterations"] < MAX_ITERATIONS:
            result = answer_question(state["project_id"], state["query"])
            state["answer"] = result["answer"]

            confidence = compute_confidence(
                query_vector=result["query_vector"],
                retrieved_vectors=result["retrieved_vectors"],
            )
            state["confidence"] = confidence

            decision = critic_agent(state)

            trace.append({
                "iteration":  state["iterations"],
                "confidence": confidence,
                "decision":   decision["action"],
            })

            logging.info(
                f"[query_worker] job={job_id} "
                f"iter={state['iterations']} "
                f"conf={confidence:.3f} "
                f"decision={decision['action']}"
            )

            if decision["action"] == "accept":
                break

            state["query"] = (
                f"Original Question:\n{state['original_query']}\n\n"
                f"Previous Answer (needs improvement):\n{state['answer']}\n\n"
                "Provide a more accurate answer with specific code references "
                "(file name, function name, line numbers)."
            )
            state["iterations"] += 1

        publish_query_complete(
            user_id=user_id,
            job_id=job_id,
            answer=state["answer"] or "No answer found.",
            confidence=state["confidence"],
            sources=result.get("sources", []),
            trace=trace,
        )

        logging.info(f"[query_worker] Job {job_id} completed")
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        logging.error(f"[query_worker] Job {job_id} failed: {exc}")
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
"""
app.py — FastAPI entry point for the CodeMind AI service

Phase 1 fixes applied:
- project_id is validated before every Qdrant and file system operation
- Cleanup endpoint validates project_id before path operations
- Consistent response shape: always returns { answer, confidence, iterations, sources, trace }
- Health endpoint includes Qdrant connectivity check
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import shutil
import os
import stat
import re
import logging

from rag.rag_engine import index_repo, answer_question
from graph.critic import critic_agent

import numpy as np

def compute_confidence(query_vector, retrieved_vectors):
    """
    Cosine similarity between query embedding and retrieved chunk embeddings.
    NOTE: This measures retrieval relevance, not answer correctness.
    A high score means the retrieved chunks are relevant to the question.
    It does NOT guarantee the LLM answer is factually correct.
    """
    if not retrieved_vectors:
        return 0.0
    q = query_vector[0]
    q_norm = q / (np.linalg.norm(q) + 1e-10)
    sims = []
    for v in retrieved_vectors:
        v_norm = v / (np.linalg.norm(v) + 1e-10)
        sims.append(float(np.dot(q_norm, v_norm)))
    return float(np.mean(sims))


logging.basicConfig(level=logging.INFO)
app = FastAPI(title="CodeMind AI Service")

TMP_REPO_PATH = "./tmp/repos"


# =============================================================================
# Validation helpers
# =============================================================================

def validate_github_url(url: str) -> bool:
    """Only allow public GitHub URLs. Prevents SSRF and path traversal."""
    pattern = r'^https://github\.com/[\w\-]+/[\w\-\.]+/?$'
    return bool(re.match(pattern, url))


def validate_project_id(project_id: str) -> bool:
    """
    FIX: project_id was used raw in file paths and Qdrant collection names.
    Only allow MongoDB ObjectId (24 hex chars) or UUID (36 chars with dashes).
    Prevents path traversal: project_id = "../../etc/passwd"
    """
    if not project_id:
        return False
    mongo_id = re.match(r'^[a-f0-9]{24}$', project_id)
    uuid_fmt  = re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', project_id)
    return bool(mongo_id or uuid_fmt)


def force_delete(func, path, exc_info):
    """Windows-safe deletion for shutil.rmtree."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


# =============================================================================
# Request models
# =============================================================================

class IndexRequest(BaseModel):
    project_id: str
    repo_url: str

class QueryRequest(BaseModel):
    project_id: str
    question: str


# =============================================================================
# Health check
# =============================================================================

@app.get("/health")
def health():
    """Liveness probe. Also checks Qdrant is reachable."""
    try:
        from rag.vector_store import get_client
        get_client().get_collections()
        qdrant_status = "ok"
    except Exception as e:
        qdrant_status = f"error: {str(e)}"

    return {"status": "ok", "qdrant": qdrant_status}


# =============================================================================
# Index repository
# =============================================================================

@app.post("/index-repo")
def index_repository(req: IndexRequest):
    """
    1. Validate GitHub URL and project_id
    2. Clone repo to ./tmp/repos/<project_id>/
    3. AST-aware chunking
    4. Embed with sentence-transformers
    5. Save to Qdrant collection project_{project_id}
    """
    if not validate_project_id(req.project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project_id format. Expected MongoDB ObjectId or UUID."
        )

    if not validate_github_url(req.repo_url):
        raise HTTPException(
            status_code=400,
            detail="Only public GitHub URLs supported. Format: https://github.com/owner/repo"
        )

    try:
        result = index_repo(req.project_id, req.repo_url)
        return result
    except Exception as e:
        logging.error(f"Indexing failed for {req.project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Query — agentic retry loop
# (replaced with LangGraph in Phase 3)
# =============================================================================

@app.post("/query")
def query_repository(req: QueryRequest):
    """
    Answers a natural language question about the indexed codebase.

    Returns consistent shape:
    { answer, confidence, iterations, sources, trace }
    """
    if not validate_project_id(req.project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project_id format."
        )

    MAX_ITERATIONS = 3

    state = {
        "project_id":     req.project_id,
        "query":          req.question,
        "original_query": req.question,
        "iterations":     0,
        "answer":         None,
        "confidence":     0.0,
    }

    trace = []
    result = {}

    while state["iterations"] < MAX_ITERATIONS:
        result = answer_question(state["project_id"], state["query"])
        state["answer"] = result["answer"]

        confidence = compute_confidence(
            query_vector=result["query_vector"],
            retrieved_vectors=result["retrieved_vectors"],
        )
        state["confidence"] = confidence

        decision = critic_agent(state)

        logging.info(
            f"[Iter {state['iterations']}] "
            f"Confidence: {confidence:.3f} | Decision: {decision['action']}"
        )

        trace.append({
            "iteration":  state["iterations"],
            "confidence": confidence,
            "decision":   decision["action"],
        })

        if decision["action"] == "accept":
            break

        state["query"] = (
            f"Original Question:\n{state['original_query']}\n\n"
            f"Previous Answer (needs improvement):\n{state['answer']}\n\n"
            "Provide a more accurate answer with specific code references "
            "(file name, function name, line numbers)."
        )
        state["iterations"] += 1

    # Consistent response shape — matches what Node.js query_controllers.js expects
    return {
        "answer":     state["answer"],
        "confidence": state["confidence"],
        "iterations": state["iterations"],
        "sources":    result.get("sources", []),
        "trace":      trace,
    }


# =============================================================================
# Cleanup — delete project artifacts
# =============================================================================

@app.post("/cleanup")
def cleanup_repo(data: dict):
    """
    Deletes all local artifacts for a project:
    - Cloned repo under ./tmp/repos/<project_id>/
    - Qdrant collection project_{project_id}

    Called when user deletes a project (not on logout).
    """
    project_id = data.get("project_id")

    # FIX: validate before using in file path or Qdrant collection name
    if not validate_project_id(project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project_id format."
        )

    # Delete cloned repo
    repo_path = os.path.join(TMP_REPO_PATH, project_id)
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path, onerror=force_delete)
        logging.info(f"Deleted repo: {repo_path}")

    # Delete Qdrant collection
    try:
        from rag.vector_store import get_client, _collection_name
        client = get_client()
        collection = _collection_name(project_id)
        if client.collection_exists(collection):
            client.delete_collection(collection)
            logging.info(f"Deleted Qdrant collection: {collection}")
    except Exception as e:
        logging.warning(f"Qdrant cleanup warning for {project_id}: {e}")

    return {"status": "deleted", "project_id": project_id}

"""
app.py — FastAPI entry point for the CodeMind AI service

What this file does:
- GET  /health   → liveness probe (Docker healthcheck uses this)
- POST /cleanup  → delete project artifacts when user deletes a project

What this file does NOT do:
- /query   → removed. Queries go: Node.js query_service → Redis → query_worker.py → react_graph.py
- /index-repo → removed. Indexing goes: Node.js project_service → Redis → index_worker.py → rag_engine.py
  Both Celery workers import rag_engine and react_graph directly — this FastAPI app is not in that path.
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
import shutil
import os
import stat
import re
import logging

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="CodeMind AI Service")

TMP_REPO_PATH = "./tmp/repos"


# =============================================================================
# Validation helper
# =============================================================================

def validate_project_id(project_id: str) -> bool:
    """
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
# Cleanup — delete project artifacts
# =============================================================================

@app.post("/cleanup")
def cleanup_repo(data: dict):
    """
    Deletes all local artifacts for a project:
    - Cloned repo under ./tmp/repos/<project_id>/
    - Qdrant collection project_{project_id}

    Called by project_controllers.js when user deletes a project.
    """
    project_id = data.get("project_id")

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
"""
search_tool.py — Semantic code search using Qdrant

Agent jab bhi codebase mein kuch dhundna chahta hai, yeh tool use karta hai.
Qdrant se top-k relevant chunks return karta hai with metadata.
"""

from rag.embeddings import generate_embeddings
from rag.vector_store import get_client, _collection_name
import logging

logger = logging.getLogger(__name__)


def search_code(project_id: str, query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search — query ko embed karo, Qdrant mein similar chunks dhundho.

    Args:
        project_id: kaun sa project search karna hai
        query:      natural language search query
        top_k:      kitne results chahiye (default 5)

    Returns:
        List of chunks with content, file, function_name, start_line, end_line
    """
    try:
        # Query ko vector mein convert karo
        query_vector = generate_embeddings([query])[0].tolist()

        client     = get_client()
        collection = _collection_name(project_id)

        # Collection exist karti hai?
        if not client.collection_exists(collection):
            logger.warning(f"[search_code] Collection {collection} does not exist")
            return []

        # Qdrant mein search karo
        results = client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )

        chunks = []
        for r in results:
            payload = r.payload or {}
            chunks.append({
                "content":       payload.get("content", ""),
                "file":          payload.get("file", ""),
                "language":      payload.get("language", ""),
                "chunk_type":    payload.get("chunk_type", ""),
                "function_name": payload.get("function_name", ""),
                "class_name":    payload.get("class_name", ""),
                "start_line":    payload.get("start_line", 0),
                "end_line":      payload.get("end_line", 0),
                "score":         r.score,
            })

        logger.info(f"[search_code] Found {len(chunks)} chunks for query: {query[:50]}")
        return chunks

    except Exception as e:
        logger.error(f"[search_code] Error: {e}")
        return []
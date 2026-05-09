"""
vector_store.py — Qdrant replacement for FAISS

Why Qdrant over FAISS:
- FAISS saves to .faiss files that die on container restart
- Qdrant persists in a Docker volume — data survives restarts
- Qdrant supports filtering by metadata (file, language, chunk_type)

Each project gets its own Qdrant collection: project_{project_id}
Same namespace-by-project_id pattern as before.
"""

import os
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

_client = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def _collection_name(project_id: str) -> str:
    return f"project_{project_id}"


def save_index(project_id: str, vectors: np.ndarray, metadata: list):
    """
    Upserts all chunk vectors for a project into Qdrant.

    Drop-in replacement for old FAISS save_index().
    Same signature — rag_engine.py needs no changes.

    Args:
        project_id: Namespaces the Qdrant collection
        vectors:    numpy array shape (num_chunks, 384)
        metadata:   list of dicts {"file": str, "content": str, ...}
                    AST chunker adds: function_name, start_line, end_line, language
    """
    client = get_client()
    collection = _collection_name(project_id)

    # Wipe and recreate collection on reindex
    if client.collection_exists(collection):
        client.delete_collection(collection)

    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )

    points = []
    for i, (vector, meta) in enumerate(zip(vectors, metadata)):
        points.append(
            PointStruct(
                id=i,
                vector=vector.tolist(),
                payload=meta,
            )
        )

    # Batch upsert in chunks of 100 to stay within Qdrant payload limits
    batch_size = 100
    for start in range(0, len(points), batch_size):
        client.upsert(
            collection_name=collection,
            points=points[start:start + batch_size]
        )


def load_index(project_id: str):
    """
    Returns (QdrantIndexWrapper, QdrantMetadataProxy).

    Mimics the old FAISS (index, metadata) tuple so rag_engine.py
    needs zero changes:
        index, metadata = load_index(project_id)
        D, I = index.search(query_vector, k)
        vec = index.reconstruct(idx)
        file = metadata[idx]["file"]
    """
    client = get_client()
    collection = _collection_name(project_id)

    if not client.collection_exists(collection):
        raise FileNotFoundError(
            f"No index found for project {project_id}. Index it first."
        )

    return QdrantIndexWrapper(client, collection), QdrantMetadataProxy(client, collection)


class QdrantIndexWrapper:
    """
    Mimics FAISS index API used in rag_engine.py:
        D, I = index.search(query_vector, k)
        vec  = index.reconstruct(int_idx)
    """

    def __init__(self, client: QdrantClient, collection: str):
        self._client = client
        self._collection = collection
        self._last_results = {}

    def search(self, query_vector: np.ndarray, k: int):
        """
        query_vector shape: (1, 384) — same as FAISS expects.
        Returns D, I as nested lists matching FAISS output shape [[...]], [[...]]
        """
        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector[0].tolist(),  # flatten (1,384) → (384,)
            limit=k,
            with_payload=True,
            with_vectors=True,
        )

        # Cache for reconstruct() — avoids second network call
        self._last_results = {r.id: r for r in results}

        # Convert cosine similarity (higher=better) to distance (lower=better)
        distances = [[1.0 - r.score for r in results]]
        indices   = [[r.id          for r in results]]

        return distances, indices

    def reconstruct(self, idx: int) -> np.ndarray:
        """Returns stored vector for point idx — used by confidence scorer."""
        if idx in self._last_results:
            return np.array(self._last_results[idx].vector, dtype="float32")

        # Fallback fetch if called outside of a search context
        results = self._client.retrieve(
            collection_name=self._collection,
            ids=[idx],
            with_vectors=True,
        )
        if not results:
            return np.zeros(VECTOR_SIZE, dtype="float32")
        return np.array(results[0].vector, dtype="float32")


class QdrantMetadataProxy:
    """
    Mimics list-style metadata access from rag_engine.py:
        file = metadata[idx]["file"]
        code = metadata[idx]["content"]

    Fetches payload from Qdrant by point ID with local cache.
    """

    def __init__(self, client: QdrantClient, collection: str):
        self._client = client
        self._collection = collection
        self._cache: dict = {}

    def __getitem__(self, idx: int) -> dict:
        if idx in self._cache:
            return self._cache[idx]

        results = self._client.retrieve(
            collection_name=self._collection,
            ids=[idx],
            with_payload=True,
        )
        if not results:
            return {"file": "unknown", "content": ""}

        payload = results[0].payload
        self._cache[idx] = payload
        return payload

    def __len__(self) -> int:
        info = self._client.get_collection(self._collection)
        return info.points_count

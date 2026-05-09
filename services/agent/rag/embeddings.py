"""
embeddings.py — Local sentence-transformers embeddings

Phase 1 fix: removed dependency on external STAPI container.
Loads all-MiniLM-L6-v2 directly inside the agent container.

Why this is better:
- No separate stapi container to manage
- No network call overhead per embedding
- Model is loaded once at startup and cached in memory
- Works fully offline after first docker build

Trade-off: agent container is ~400MB larger (model download at build time).
This is fine for Phase 1. In Phase 6+ we can split it back out if needed.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

# Loaded once when the module is first imported — stays in memory
# FastAPI workers share this via the module cache
_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def generate_embeddings(texts) -> np.ndarray:
    """
    Generate embeddings for a list of text strings.

    Args:
        texts: str or list of str

    Returns:
        numpy array shape (len(texts), 384) dtype float32
        Same shape as before — rag_engine.py and vector_store.py unchanged.
    """
    if isinstance(texts, str):
        texts = [texts]

    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return vectors.astype("float32")

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim, same as MiniLM

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model

def generate_embeddings(texts) -> np.ndarray:
    if isinstance(texts, str):
        texts = [texts]
    model = _get_model()
    vectors = list(model.embed(texts))
    return np.array(vectors, dtype="float32")

_model = TextEmbedding(MODEL_NAME)

import hashlib
import math
import re
from typing import Protocol


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:  # lazy: heavy import and model load
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder. For offline tests only."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            v = [0.0] * self.dim
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / norm for x in v])
        return vecs


def build_embedder(backend: str, model_name: str) -> Embedder:
    if backend == "hash":
        return HashEmbedder()
    return SentenceTransformerEmbedder(model_name)

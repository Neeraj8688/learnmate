from ..schemas import Source
from .vectorstore import VectorStore


def retrieve(store: VectorStore, query: str, top_k: int, min_relevance: float) -> list[Source]:
    """Return only chunks whose cosine similarity meets the relevance floor."""
    return [s for s in store.query(query, top_k) if s.score >= min_relevance]

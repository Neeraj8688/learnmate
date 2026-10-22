import chromadb

from ..schemas import DocumentInfo, Source
from .chunking import Chunk
from .embeddings import Embedder


def _where(user_id: int, document_id: str | None = None) -> dict:
    if document_id:
        return {"$and": [{"user_id": user_id}, {"document_id": document_id}]}
    return {"user_id": user_id}


class VectorStore:
    """Shared Chroma collection. EVERY read/write is filtered by user_id (tenant isolation)."""

    def __init__(self, persist_path: str, embedder: Embedder):
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.col = self.client.get_or_create_collection("notes", metadata={"hnsw:space": "cosine"})

    def add_document(self, user_id: int, doc_id: str, filename: str, chunks: list[Chunk]) -> None:
        self.col.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=self.embedder.embed([c.text for c in chunks]),
            metadatas=[
                {"user_id": user_id, "document_id": doc_id, "document_name": filename,
                 "page": c.page if c.page is not None else -1, "chunk_index": c.index}
                for c in chunks
            ],
        )

    def query(self, user_id: int, text: str, top_k: int, document_id: str | None = None) -> list[Source]:
        where = _where(user_id, document_id)
        n = len(self.col.get(where=where, include=[])["ids"])
        if n == 0:
            return []
        res = self.col.query(query_embeddings=self.embedder.embed([text]),
                             n_results=min(top_k, n), where=where)
        out = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                        res["metadatas"][0], res["distances"][0]):
            out.append(Source(
                chunk_id=cid, document_id=meta["document_id"], document_name=meta["document_name"],
                page=meta["page"] if meta["page"] >= 0 else None, excerpt=doc,
                score=round(1.0 - dist, 4)))  # cosine similarity
        return out

    def list_documents(self, user_id: int) -> list[DocumentInfo]:
        metas = self.col.get(where=_where(user_id), include=["metadatas"])["metadatas"]
        agg: dict[str, DocumentInfo] = {}
        for m in metas:
            d = agg.setdefault(m["document_id"], DocumentInfo(
                document_id=m["document_id"], filename=m["document_name"], chunks=0))
            d.chunks += 1
        return list(agg.values())

    def delete_document(self, user_id: int, doc_id: str) -> int:
        where = _where(user_id, doc_id)
        n = len(self.col.get(where=where, include=[])["ids"])
        if n:
            self.col.delete(where=where)
        return n

    def delete_all(self, user_id: int) -> None:
        self.col.delete(where=_where(user_id))

    def sample_chunks(self, user_id: int, document_id: str | None, limit: int) -> list[Source]:
        """Evenly spaced chunks (no query), used to build quizzes over a whole document."""
        r = self.col.get(include=["documents", "metadatas"], where=_where(user_id, document_id))
        items = sorted(zip(r["ids"], r["documents"], r["metadatas"]),
                       key=lambda t: (t[2]["document_id"], t[2]["chunk_index"]))
        if len(items) > limit:
            step = len(items) / limit
            items = [items[int(i * step)] for i in range(limit)]
        return [Source(chunk_id=cid, document_id=m["document_id"], document_name=m["document_name"],
                       page=m["page"] if m["page"] >= 0 else None, excerpt=doc, score=1.0)
                for cid, doc, m in items]


class ScopedStore:
    """A VectorStore bound to one user, so services cannot forget the tenant filter."""

    def __init__(self, store: VectorStore, user_id: int):
        self.s, self.uid = store, user_id

    def add_document(self, doc_id, filename, chunks): return self.s.add_document(self.uid, doc_id, filename, chunks)
    def query(self, text, top_k, document_id=None): return self.s.query(self.uid, text, top_k, document_id)
    def list_documents(self): return self.s.list_documents(self.uid)
    def delete_document(self, doc_id): return self.s.delete_document(self.uid, doc_id)
    def delete_all(self): return self.s.delete_all(self.uid)
    def sample_chunks(self, document_id, limit): return self.s.sample_chunks(self.uid, document_id, limit)

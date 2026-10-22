from dataclasses import dataclass

from .extraction import Page


@dataclass
class Chunk:
    chunk_id: str
    page: int | None
    index: int
    text: str


def split_text(text: str, size: int, overlap: int) -> list[str]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    text = " ".join(text.split())
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)  # avoid mid-word cuts
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_pages(doc_id: str, pages: list[Page], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for piece in split_text(page.text, size, overlap):
            n = len(chunks)
            tag = f"p{page.number}" if page.number else "p0"
            chunks.append(Chunk(f"{doc_id}:{tag}:c{n}", page.number, n, piece))
    return chunks

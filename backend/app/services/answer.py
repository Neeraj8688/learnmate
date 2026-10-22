"""Grounded-answer helpers: numbered sources in, clean citations out.

The model is shown sources as [1], [2]... (never internal chunk IDs), and anything it writes that
looks like a chunk ID or an out-of-range citation is repaired or removed afterwards, so citations
in the answer always point at passages that were actually retrieved."""
import re

from ..schemas import Source

CHUNK_ID_RE = re.compile(r"\[?\s*`?([0-9a-f]{6,}:p\d+:c\d+)`?\s*\]?")
CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def number_sources(sources: list[Source]) -> list[Source]:
    for i, s in enumerate(sources, 1):
        s.ref = i
    return sources


def source_label(s: Source) -> str:
    return s.document_name + (f", page {s.page}" if s.page else "")


def build_grounded_prompt(question: str, sources: list[Source]) -> str:
    ctx = "\n\n".join(f"[{s.ref}] ({source_label(s)})\n{s.excerpt}" for s in sources)
    return (
        "You are a careful study assistant. Answer ONLY using the numbered sources in CONTEXT. "
        "If they do not contain the answer, say you cannot find it in the student's notes - do not "
        "guess. Cite supporting sources inline with their numbers like [1] or [2]; only use numbers "
        "that appear in CONTEXT and never invent sources. Do not mention file names, page numbers or "
        "internal IDs in the text. Format with Markdown (headings, lists, tables, bold). Write math "
        "in LaTeX: $...$ inline and $$...$$ for display equations.\n\n"
        f"CONTEXT:\n{ctx}\n\nQUESTION: {question}\nANSWER:"
    )


def clean_answer(text: str, sources: list[Source]) -> str:
    """Turn stray chunk IDs into [n] (or drop them) and remove citations to nonexistent sources."""
    by_id = {s.chunk_id: s.ref for s in sources}

    def fix_id(m: re.Match) -> str:
        ref = by_id.get(m.group(1))
        return f"[{ref}]" if ref else ""

    text = CHUNK_ID_RE.sub(fix_id, text)
    valid = {s.ref for s in sources}

    def fix_cite(m: re.Match) -> str:
        keep = [n for n in (int(x) for x in re.split(r"\s*,\s*", m.group(1))) if n in valid]
        return f"[{', '.join(map(str, keep))}]" if keep else ""

    text = CITE_RE.sub(fix_cite, text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r" {2,}", " ", text)).strip()

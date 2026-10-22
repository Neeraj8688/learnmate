import pytest

from app.config import Settings
from app.main import create_app
from app.services.chunking import chunk_pages, split_text
from app.services.extraction import ExtractionError, Page, extract
from fastapi.testclient import TestClient
from .conftest import authed, login, make_pdf

PAGES = [
    "Photosynthesis converts light energy into glucose inside chloroplasts using chlorophyll.",
    "TCP is a reliable connection oriented transport protocol with acknowledgements and retransmission.",
]


def upload(client, name, data, ctype="application/pdf"):
    return client.post("/documents", files={"file": (name, data, ctype)})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["server_llm_available"] is False


def test_chunk_overlap_and_size():
    text = " ".join(f"word{i}" for i in range(300))
    parts = split_text(text, 200, 40)
    assert len(parts) > 1 and all(len(p) <= 200 for p in parts)
    assert parts[0].split()[-1] in parts[1]  # overlap carries text forward


def test_chunk_overlap_validation():
    with pytest.raises(ValueError):
        split_text("abc", 10, 10)


def test_pdf_pages_preserved():
    pages = extract("a.pdf", make_pdf(PAGES))
    assert [p.number for p in pages] == [1, 2]
    chunks = chunk_pages("d1", pages, 800, 100)
    assert {c.page for c in chunks} == {1, 2}


def test_rejects_bad_type(client):
    assert upload(client, "x.docx", b"hi").status_code == 415


def test_rejects_fake_pdf(client):
    assert upload(client, "x.pdf", b"not a pdf").status_code == 422


def test_rejects_oversize(client):
    r = upload(client, "big.txt", b"a" * (1024 * 1024 + 5), "text/plain")
    assert r.status_code == 413


def test_rejects_empty_and_blank_pdf(client):
    assert upload(client, "e.txt", b"   ", "text/plain").status_code == 422
    assert upload(client, "blank.pdf", make_blank_pdf()).status_code == 422


def make_blank_pdf():
    import pymupdf
    d = pymupdf.open(); d.new_page(); return d.tobytes()


def test_search_returns_page_metadata(client):
    assert upload(client, "notes.pdf", make_pdf(PAGES)).status_code == 201
    res = client.post("/search", json={"query": "how does TCP provide reliable delivery"}).json()["results"]
    assert res and res[0]["page"] == 2 and res[0]["document_name"] == "notes.pdf"
    assert "TCP" in res[0]["excerpt"] and res[0]["chunk_id"]


def test_txt_has_no_page(client):
    upload(client, "n.txt", b"Mitochondria produce ATP through cellular respiration.", "text/plain")
    res = client.post("/search", json={"query": "mitochondria ATP"}).json()["results"]
    assert res[0]["page"] is None


def test_chat_insufficient_evidence(client):
    upload(client, "notes.pdf", make_pdf(PAGES))
    r = client.post("/chat", json={"question": "Who won the 1998 football world cup?"}).json()
    assert r["status"] == "insufficient_evidence" and r["sources"] == []


def test_chat_empty_index(client):
    r = client.post("/chat", json={"question": "anything at all"}).json()
    assert r["status"] == "insufficient_evidence"


def test_chat_missing_key_safe(client):
    upload(client, "notes.pdf", make_pdf(PAGES))
    r = client.post("/chat", json={"question": "photosynthesis converts light energy into glucose"}).json()
    assert r["status"] == "llm_not_configured" and r["sources"]


def test_chat_with_fake_llm(settings):
    app = create_app(settings)

    class Fake:
        configured = True
        def generate(self, prompt):
            assert "CONTEXT" in prompt
            return "Answer [x]"

    app.state.llm = Fake()
    c = authed(app)
    upload(c, "notes.pdf", make_pdf(PAGES))
    r = c.post("/chat", json={"question": "photosynthesis converts light energy into glucose"}).json()
    assert r["status"] == "answered" and r["answer"] == "Answer [x]" and r["sources"][0]["page"] == 1


def test_llm_failure_is_502_without_key_leak(settings):
    from app.llm import LLMError
    app = create_app(settings)

    class Bad:
        configured = True
        def generate(self, prompt):
            raise LLMError("LLM request failed: HTTPStatusError")

    app.state.llm = Bad()
    c = authed(app)
    upload(c, "notes.pdf", make_pdf(PAGES))
    r = c.post("/chat", json={"question": "photosynthesis converts light energy into glucose"})
    assert r.status_code == 502


def test_persistence_across_restart(settings):
    c1 = authed(create_app(settings))
    upload(c1, "notes.pdf", make_pdf(PAGES))
    c2 = login(create_app(settings))
    assert len(c2.get("/documents").json()) == 1


def test_delete_document(client):
    doc = upload(client, "notes.pdf", make_pdf(PAGES)).json()["document_id"]
    assert client.delete(f"/documents/{doc}").status_code == 200
    assert client.delete(f"/documents/{doc}").status_code == 404
    assert client.get("/documents").json() == []

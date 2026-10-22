import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 780), text, fontsize=11)
    return doc.tobytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None, embedding_backend="hash", min_relevance=0.25,
        chroma_persist_directory=str(tmp_path / "chroma"), sqlite_path=str(tmp_path / "t.db"), upload_max_mb=1, rate_general_per_min=10000, rate_llm_per_min=10000, rate_upload_per_min=10000, rate_auth_per_min=10000,
    )


PASSWORD = "password123"


def authed(app, email="a@example.com"):
    """TestClient with a freshly registered user's bearer token attached."""
    c = TestClient(app)
    r = c.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    c.headers.update({"Authorization": "Bearer " + r.json()["access_token"]})
    return c


def login(app, email="a@example.com"):
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": "Bearer " + r.json()["access_token"]})
    return c


@pytest.fixture
def client(settings):
    return authed(create_app(settings))

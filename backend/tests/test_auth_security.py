import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import hash_password, verify_password, make_token, decode_token
from .conftest import PASSWORD, authed, make_pdf
from .test_day2 import FakeLLM, PAGES


def up(c, name="n.pdf", data=None):
    return c.post("/documents", files={"file": (name, data or make_pdf(PAGES), "application/pdf")})


def test_password_hashing():
    h = hash_password("secret123")
    assert h != "secret123" and verify_password("secret123", h) and not verify_password("secret124", h)
    assert not verify_password("x", "garbage")


def test_token_roundtrip_and_tamper():
    t = make_token("s3cret" * 6, 7, 1)
    assert decode_token("s3cret" * 6, t) == 7
    assert decode_token("other" * 8, t) is None and decode_token("s3cret" * 6, t + "x") is None
    assert decode_token("s3cret" * 6, make_token("s3cret" * 6, 7, -1)) is None  # expired


def test_endpoints_require_auth(settings):
    c = TestClient(create_app(settings))
    for method, path in [("get", "/documents"), ("post", "/chat"), ("post", "/quizzes"),
                         ("get", "/attempts"), ("get", "/weak-topics"), ("get", "/me"),
                         ("post", "/agent"), ("get", "/revision-plan")]:
        assert getattr(c, method)(path).status_code == 401, path
    assert c.get("/documents", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert c.get("/health").status_code == 200


def test_register_login_rules(settings):
    app = create_app(settings)
    c = TestClient(app)
    assert c.post("/auth/register", json={"email": "bad", "password": PASSWORD}).status_code == 422
    assert c.post("/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 422
    assert c.post("/auth/register", json={"email": "A@B.co", "password": PASSWORD}).status_code == 201
    assert c.post("/auth/register", json={"email": "a@b.co", "password": PASSWORD}).status_code == 409  # case-insens.
    assert c.post("/auth/login", json={"email": "a@b.co", "password": "wrongpass1"}).status_code == 401
    assert c.post("/auth/login", json={"email": "nobody@b.co", "password": PASSWORD}).status_code == 401
    assert c.post("/auth/login", json={"email": "a@b.co", "password": PASSWORD}).status_code == 200


def test_registration_can_be_closed(tmp_path):
    s = Settings(_env_file=None, embedding_backend="hash", allow_registration=False,
                 chroma_persist_directory=str(tmp_path / "c"), sqlite_path=str(tmp_path / "s.db"))
    r = TestClient(create_app(s)).post("/auth/register", json={"email": "a@b.co", "password": PASSWORD})
    assert r.status_code == 403


def test_users_cannot_see_each_others_data(settings):
    app = create_app(settings); app.state.llm = FakeLLM()
    alice, bob = authed(app, "alice@x.com"), authed(app, "bob@x.com")
    doc = up(alice).json()["document_id"]
    qid = alice.post("/quizzes", json={}).json()["quiz_id"]
    alice.post(f"/quizzes/{qid}/submit", json={"answers": [{"question_id": 0, "selected_index": 1}]})
    # Bob sees nothing of Alice's
    assert bob.get("/documents").json() == []
    q = "photosynthesis converts light energy into glucose using chlorophyll"
    assert bob.post("/search", json={"query": q}).json()["results"] == []
    assert bob.post("/chat", json={"question": q}).json()["status"] == "insufficient_evidence"
    assert bob.get(f"/quizzes/{qid}").status_code == 404
    assert bob.post(f"/quizzes/{qid}/submit", json={"answers": []}).status_code == 404
    assert bob.get("/attempts").json() == [] and bob.get("/weak-topics").json()["topics"] == []
    assert bob.delete(f"/documents/{doc}").status_code == 404
    assert bob.post("/quizzes", json={"document_id": doc}).status_code == 422
    # ...and Alice's data is intact
    assert len(alice.get("/documents").json()) == 1 and len(alice.get("/attempts").json()) == 1


def test_task_ownership(settings):
    app = create_app(settings); app.state.llm = FakeLLM()
    alice, bob = authed(app, "alice@x.com"), authed(app, "bob@x.com")
    up(alice)
    qid = alice.post("/quizzes", json={"num_questions": 4}).json()["quiz_id"]
    for _ in range(3):
        alice.post(f"/quizzes/{qid}/submit", json={"answers": [{"question_id": i, "selected_index": 0} for i in range(4)]})
    tid = alice.post("/revision-plan", json={}).json()["tasks"][0]["task_id"]
    assert bob.patch(f"/revision-tasks/{tid}", json={"status": "done"}).status_code == 404
    assert alice.patch(f"/revision-tasks/{tid}", json={"status": "done"}).status_code == 200
    assert bob.get("/revision-plan").json()["tasks"] == []


def test_document_limits(tmp_path):
    s = Settings(_env_file=None, embedding_backend="hash", max_docs_per_user=2, max_chunks_per_doc=1,
                 chroma_persist_directory=str(tmp_path / "c"), sqlite_path=str(tmp_path / "s.db"),
                 rate_general_per_min=1000, rate_upload_per_min=1000, rate_auth_per_min=1000)
    c = authed(create_app(s))
    long_txt = ("word " * 600).encode()
    r = c.post("/documents", files={"file": ("big.txt", long_txt, "text/plain")})
    assert r.status_code == 413 and "too large" in r.json()["detail"].lower()
    for i in range(2):
        assert c.post("/documents", files={"file": (f"{i}.txt", b"short note here", "text/plain")}).status_code == 201
    assert c.post("/documents", files={"file": ("3.txt", b"short note here", "text/plain")}).status_code == 409


def test_rate_limits(tmp_path):
    s = Settings(_env_file=None, embedding_backend="hash", rate_llm_per_min=3, rate_auth_per_min=4,
                 rate_general_per_min=1000, chroma_persist_directory=str(tmp_path / "c"),
                 sqlite_path=str(tmp_path / "s.db"))
    app = create_app(s)
    c = authed(app)                                   # 1 auth hit
    codes = [c.post("/chat", json={"question": "anything at all"}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = c.post("/chat", json={"question": "anything at all"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    anon = TestClient(app)
    bad = [anon.post("/auth/login", json={"email": "x@y.co", "password": "wrongpass1"}).status_code for _ in range(5)]
    assert 429 in bad and bad[0] == 401


def _budget_app(tmp_path, per_user=2, global_cap=100):
    s = Settings(_env_file=None, embedding_backend="hash", min_relevance=0.25,
                 daily_llm_calls_per_user=per_user, daily_llm_calls_global=global_cap,
                 rate_general_per_min=1000, rate_llm_per_min=1000, rate_auth_per_min=1000,
                 chroma_persist_directory=str(tmp_path / "c"), sqlite_path=str(tmp_path / "s.db"))
    app = create_app(s)
    app.state.llm = FakeLLM("fine")   # server key
    return app


Q = {"question": "photosynthesis converts light energy into glucose using chlorophyll"}


def test_daily_budget_per_user_then_personal_key_unblocks(tmp_path, monkeypatch):
    import app.deps as deps
    app = _budget_app(tmp_path, per_user=2)
    c = authed(app); up(c)
    assert [c.post("/chat", json=Q).status_code for _ in range(2)] == [200, 200]
    r = c.post("/chat", json=Q)
    assert r.status_code == 429 and r.json()["code"] == "demo_limit_reached"
    assert "Gemini API key" in r.json()["detail"]
    assert c.get("/me").json()["usage"]["server_calls_today"] == 2
    monkeypatch.setattr(deps, "build_provider", lambda *a: FakeLLM("own key answer"))
    r = c.post("/chat", json=Q, headers={"X-LLM-Key": "AIza-personal-key-1234"})
    assert r.status_code == 200 and r.json()["answer"] == "own key answer"
    assert c.get("/me").json()["usage"]["server_calls_today"] == 2   # personal calls not counted


def test_global_budget(tmp_path):
    app = _budget_app(tmp_path, per_user=50, global_cap=3)
    a, b = authed(app, "a@x.com"), authed(app, "b@x.com")
    up(a); up(b)
    assert [a.post("/chat", json=Q).status_code for _ in range(2)] == [200, 200]
    assert b.post("/chat", json=Q).status_code == 200
    r = b.post("/chat", json=Q)
    assert r.status_code == 429 and "shared demo allowance" in r.json()["detail"]


def test_budget_on_quiz_and_agent(tmp_path):
    app = _budget_app(tmp_path, per_user=0)
    c = authed(app); up(c)
    assert c.post("/quizzes", json={}).status_code == 429
    r = c.post("/agent", json={"message": Q["question"]})
    assert r.status_code == 429 and r.json()["code"] == "demo_limit_reached"


def test_delete_account_removes_everything(settings):
    app = create_app(settings); app.state.llm = FakeLLM()
    c = authed(app)
    up(c); qid = c.post("/quizzes", json={}).json()["quiz_id"]
    c.post(f"/quizzes/{qid}/submit", json={"answers": []})
    assert c.delete("/me").status_code == 200
    assert app.state.store.list_documents(1) == []
    for t in ("users", "quizzes", "attempts", "attempt_answers"):
        assert app.state.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] == 0
    assert c.get("/documents").status_code == 401   # token no longer maps to a user


def test_secrets_persist_across_restart(settings):
    a1 = create_app(settings)
    c1 = authed(a1)
    a2 = create_app(settings)       # no JWT_SECRET env: must reuse the persisted one
    c2 = TestClient(a2, headers=c1.headers)
    assert c2.get("/me").status_code == 200


def test_session_key_header_bypasses_budget_and_is_not_stored(tmp_path, monkeypatch):
    import app.deps as deps
    app = _budget_app(tmp_path, per_user=0)            # server budget already exhausted
    c = authed(app); up(c)
    assert c.get("/me").json()["server_ai_status"] == "user_quota_used"
    assert c.post("/chat", json=Q).status_code == 429
    seen = {}
    def fake_build(name, key, model, timeout=45):
        seen.update(name=name, key=key, model=model); return FakeLLM("session answer")
    monkeypatch.setattr(deps, "build_provider", fake_build)
    h = {"X-LLM-Key": "sk-session-key-5555"}
    r = c.post("/chat", json=Q, headers=h)
    assert r.status_code == 200 and r.json()["answer"] == "session answer"
    assert seen["name"] == "gemini" and seen["key"] == "sk-session-key-5555"
    assert "sk-session-key-5555" not in r.text
    assert app.state.db.query("SELECT llm_key_enc FROM users")[0]["llm_key_enc"] is None   # not persisted
    assert c.get("/me").json()["usage"]["server_calls_today"] == 0
    assert c.post("/llm/check", headers=h).json() == {"ok": True, "source": "personal"}


def test_bad_session_headers_rejected(client):
    for h in ({"X-LLM-Provider": "evil", "X-LLM-Key": "abcdefgh12"},
              {"X-LLM-Provider": "gemini", "X-LLM-Key": "short"}):
        assert client.get("/documents", headers=h).status_code == 422


def test_ai_status_values(tmp_path):
    app = _budget_app(tmp_path, per_user=1, global_cap=100)
    c = authed(app); up(c)
    assert c.get("/me").json()["server_ai_status"] == "ok"
    c.post("/chat", json=Q)
    assert c.get("/me").json()["server_ai_status"] == "user_quota_used"
    s2 = Settings(_env_file=None, embedding_backend="hash", chroma_persist_directory=str(tmp_path / "c2"),
                  sqlite_path=str(tmp_path / "s2.db"))
    assert authed(create_app(s2)).get("/me").json()["server_ai_status"] == "not_configured"
    app3 = _budget_app(tmp_path / "x", per_user=50, global_cap=1)
    c3 = authed(app3); up(c3); c3.post("/chat", json=Q)
    assert c3.get("/me").json()["server_ai_status"] == "site_quota_used"

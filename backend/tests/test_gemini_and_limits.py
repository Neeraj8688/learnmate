"""Mocked Gemini behaviour: classification of every failure mode, shared-key vs personal-key rules,
limits, citations and production safety. No real network or key is used."""
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.llm import gemini as gem
from app.main import create_app
from app.schemas import Source
from app.services.answer import clean_answer, number_sources
from .conftest import PASSWORD, authed, make_pdf
from .test_day2 import PAGES

SHARED, PERSONAL = "SHARED-KEY-SENTINEL-1111", "PERSONAL-KEY-SENTINEL-2222"
Q = {"question": "photosynthesis converts light energy into glucose using chlorophyll"}
URL = "https://generativelanguage.googleapis.com/v1beta/models/m:generateContent"


def ok_body(text="Hello **world** [1]"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def resp(status, body=None, text=None):
    return httpx.Response(status, request=httpx.Request("POST", URL),
                          text=text if text is not None else json.dumps(body if body is not None else {}))


def err429(msg, details=None):
    return resp(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": msg,
                                "details": details or []}})


class FakePost:
    def __init__(self):
        self.queue, self.calls = [], []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "key": (headers or {}).get("x-goog-api-key"), "body": json})
        item = self.queue[0] if len(self.queue) == 1 else self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def post(monkeypatch):
    fp = FakePost()
    monkeypatch.setattr(gem.httpx, "post", fp)
    monkeypatch.setattr(gem.time, "sleep", lambda s: None)
    return fp


def make_settings(tmp_path, **kw):
    base = dict(_env_file=None, embedding_backend="hash", min_relevance=0.25, gemini_api_key=SHARED,
                gemini_model="m", chroma_persist_directory=str(tmp_path / "c"),
                sqlite_path=str(tmp_path / "s.db"), rate_general_per_min=10000, rate_llm_per_min=10000,
                rate_upload_per_min=10000, rate_auth_per_min=10000)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def ctx(tmp_path, post):
    app = create_app(make_settings(tmp_path))
    c = authed(app)
    c.post("/documents", files={"file": ("bio.pdf", make_pdf(PAGES), "application/pdf")})
    return app, c


PH = {"X-LLM-Key": PERSONAL}


# ---------- success path, grounding, secrecy ----------
def test_shared_key_success_with_numbered_grounded_prompt(ctx, post):
    app, c = ctx
    post.queue = [resp(200, ok_body())]
    r = c.post("/chat", json=Q).json()
    assert r["status"] == "answered" and r["answer"] == "Hello **world** [1]"
    assert r["sources"][0]["ref"] == 1 and r["sources"][0]["document_name"] == "bio.pdf"
    prompt = post.calls[0]["body"]["contents"][0]["parts"][0]["text"]
    assert "CONTEXT" in prompt and "[1] (bio.pdf, page 1)" in prompt
    import re
    assert not re.search(r"[0-9a-f]{6,}:p\d+:c\d+", prompt)        # internal chunk ids never shown to the model
    assert post.calls[0]["key"] == SHARED and SHARED not in post.calls[0]["url"]   # header, not URL


def test_shared_key_never_appears_in_any_response(ctx, post):
    app, c = ctx
    bodies = [c.get("/health").text, c.get("/me").text, c.get("/documents").text, app.openapi().__str__()]
    post.queue = [resp(200, ok_body())]
    bodies.append(c.post("/chat", json=Q).text)
    post.queue = [resp(403, {"error": {"status": "PERMISSION_DENIED", "message": SHARED}})]
    bodies.append(c.post("/chat", json=Q).text)
    post.queue = [err429("quota " + SHARED)]
    bodies.append(c.post("/chat", json=Q).text)
    assert not any(SHARED in b for b in bodies)


def test_unsupported_question_does_not_call_gemini(ctx, post):
    app, c = ctx
    r = c.post("/chat", json={"question": "Who won the 1998 football world cup final match?"}).json()
    assert r["status"] == "insufficient_evidence" and r["sources"] == [] and post.calls == []


# ---------- classification ----------
def test_confirmed_daily_quota_then_shared_key_paused(ctx, post):
    app, c = ctx
    post.queue = [err429("Quota exceeded", [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}])]
    r = c.post("/chat", json=Q)
    assert r.status_code == 429 and r.json()["code"] == "shared_quota_exhausted"
    assert "Gemini API key" in r.json()["detail"]
    n = len(post.calls)
    r2 = c.post("/chat", json=Q)                                   # provider is NOT called again
    assert r2.json()["code"] == "shared_quota_exhausted" and len(post.calls) == n
    assert c.get("/me").json()["server_ai_status"] == "site_quota_used"
    assert c.get("/documents").json()                               # documents/chat state untouched


def test_per_minute_429_is_temporary_not_quota(ctx, post):
    app, c = ctx
    post.queue = [err429("slow down", [{"retryDelay": "17s", "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"}]}])]
    r = c.post("/chat", json=Q)
    assert r.status_code == 429 and r.json()["code"] == "provider_rate_limited"
    assert r.headers["Retry-After"] == "17"
    assert c.get("/me").json()["server_ai_status"] == "ok"
    assert c.get("/me").json()["usage"]["server_calls_today"] == 0   # allowance refunded


def test_ambiguous_429_escalates_after_strikes(tmp_path, post):
    app = create_app(make_settings(tmp_path, quota_confirm_strikes=3))
    c = authed(app); c.post("/documents", files={"file": ("bio.pdf", make_pdf(PAGES), "application/pdf")})
    post.queue = [err429("Resource has been exhausted")]
    codes = [c.post("/chat", json=Q).json()["code"] for _ in range(3)]
    assert codes == ["provider_rate_limited", "provider_rate_limited", "shared_quota_exhausted"]


def test_503_retries_once_then_succeeds(ctx, post):
    app, c = ctx
    post.queue = [resp(503, {"error": {"status": "UNAVAILABLE"}}), resp(200, ok_body("recovered"))]
    r = c.post("/chat", json=Q).json()
    assert r["answer"] == "recovered" and len(post.calls) == 2


def test_persistent_503_is_temporary_error_not_quota_dialog(ctx, post):
    app, c = ctx
    post.queue = [resp(503, {"error": {"status": "UNAVAILABLE"}})]
    r = c.post("/chat", json=Q)
    assert r.status_code == 503 and r.json()["code"] == "provider_unavailable" and "Retry-After" in r.headers
    assert c.get("/me").json()["usage"]["server_calls_today"] == 0       # not charged
    assert c.get("/me").json()["server_ai_status"] == "ok"               # shared key not marked exhausted


def test_network_failure(ctx, post):
    app, c = ctx
    post.queue = [httpx.ConnectError("boom " + SHARED)]
    r = c.post("/chat", json=Q)
    assert r.status_code == 502 and r.json()["code"] == "provider_network_error" and SHARED not in r.text
    post.queue = [httpx.ReadTimeout("t")]
    assert c.post("/chat", json=Q).json()["code"] == "provider_network_error"


def test_shared_key_rejected_is_server_problem_not_visitors(ctx, post):
    app, c = ctx
    post.queue = [resp(403, {"error": {"status": "PERMISSION_DENIED"}})]
    r = c.post("/chat", json=Q)
    assert r.status_code == 503 and r.json()["code"] == "server_ai_misconfigured"


def test_blocked_or_empty_answer(ctx, post):
    app, c = ctx
    post.queue = [resp(200, {"promptFeedback": {"blockReason": "SAFETY"}})]
    r = c.post("/chat", json=Q)
    assert r.status_code == 502 and r.json()["code"] == "provider_error"


def test_bad_model_name(ctx, post):
    app, c = ctx
    post.queue = [resp(404, {"error": {"status": "NOT_FOUND"}})]
    assert "model" in c.post("/chat", json=Q).json()["detail"].lower()


# ---------- personal key rules ----------
def test_personal_key_used_and_shared_untouched(ctx, post):
    app, c = ctx
    post.queue = [resp(200, ok_body("mine"))]
    r = c.post("/chat", json=Q, headers=PH).json()
    assert r["answer"] == "mine" and post.calls[-1]["key"] == PERSONAL
    assert c.get("/me").json()["usage"]["server_calls_today"] == 0
    post.queue = [resp(200, ok_body("shared again"))]
    c.post("/chat", json=Q)
    assert post.calls[-1]["key"] == SHARED                          # no personal key -> shared key


def test_invalid_personal_key_no_silent_fallback(ctx, post):
    app, c = ctx
    post.queue = [resp(400, {"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid"}})]
    r = c.post("/chat", json=Q, headers=PH)
    assert r.status_code == 400 and r.json()["code"] == "invalid_api_key" and PERSONAL not in r.text
    assert [x["key"] for x in post.calls] == [PERSONAL]            # shared key was never tried
    assert c.post("/llm/check", headers=PH).json()["code"] == "invalid_api_key"


def test_personal_quota_exhausted_does_not_fall_back_or_pause_shared(ctx, post):
    app, c = ctx
    post.queue = [err429("Quota exceeded", [{"violations": [{"quotaId": "RequestsPerDay"}]}])]
    r = c.post("/chat", json=Q, headers=PH)
    assert r.status_code == 429 and r.json()["code"] == "personal_quota_exhausted"
    assert {x["key"] for x in post.calls} == {PERSONAL}
    assert c.get("/me").json()["server_ai_status"] == "ok"           # shared key unaffected


def test_personal_key_failures_are_classified_too(ctx, post):
    app, c = ctx
    post.queue = [resp(503, {})]
    assert c.post("/chat", json=Q, headers=PH).json()["code"] == "provider_unavailable"
    post.queue = [httpx.ConnectError("x")]
    assert c.post("/chat", json=Q, headers=PH).json()["code"] == "provider_network_error"


def test_personal_key_never_in_responses_or_logs(ctx, post, caplog):
    app, c = ctx
    caplog.set_level(logging.DEBUG)
    texts = []
    for q in ([resp(200, ok_body())], [resp(400, {"error": {"message": "API key not valid " + PERSONAL}})],
              [httpx.ConnectError(PERSONAL)], [err429("x " + PERSONAL)]):
        post.queue = q
        texts.append(c.post("/chat", json=Q, headers=PH).text)
    assert PERSONAL not in " ".join(texts) and PERSONAL not in caplog.text
    assert app.state.db.query("SELECT COUNT(*) n FROM users WHERE llm_key_enc IS NOT NULL")[0]["n"] == 0


def test_personal_key_requires_https_in_production(tmp_path, post):
    app = create_app(make_settings(tmp_path, environment="production", jwt_secret="x" * 40,
                                   cors_origins="https://app.example.com", trust_proxy_headers=True))
    http = authed(app)
    r = http.post("/chat", json=Q, headers=PH)
    assert r.status_code == 400 and r.json()["code"] == "https_required"
    assert post.calls == []
    post.queue = [resp(200, ok_body())]
    via_proxy = http.post("/chat", json=Q, headers={**PH, "X-Forwarded-Proto": "https"})
    assert via_proxy.status_code in (200,)                           # insufficient_evidence is also 200
    secure = TestClient(app, base_url="https://testserver", headers=dict(http.headers))
    assert secure.post("/chat", json=Q, headers=PH).status_code == 200


def test_http_keys_allowed_in_development(ctx, post):
    app, c = ctx
    post.queue = [resp(200, ok_body())]
    assert c.post("/chat", json=Q, headers=PH).status_code == 200


# ---------- demo limits ----------
def test_question_length_limits(ctx, post):
    app, c = ctx
    long_q = "photosynthesis " * 50                                  # 750 chars
    r = c.post("/chat", json={"question": long_q})
    assert r.status_code == 422 and r.json()["code"] == "question_too_long"
    assert post.calls == []
    post.queue = [resp(200, ok_body())]
    assert c.post("/chat", json={"question": long_q}, headers=PH).status_code == 200
    assert c.post("/chat", json={"question": "a" * 3000}, headers=PH).status_code == 422   # hard cap
    assert c.post("/agent", json={"message": long_q}).json()["code"] == "question_too_long"


def test_all_limits_configurable(tmp_path, post):
    s = make_settings(tmp_path, demo_max_question_chars=20, daily_llm_calls_per_user=1, upload_max_mb=1,
                      rate_llm_per_min=2)
    assert (s.demo_max_question_chars, s.daily_llm_calls_per_user, s.upload_max_mb, s.rate_llm_per_min) == (20, 1, 1, 2)
    c = authed(create_app(s))
    c.post("/documents", files={"file": ("n.pdf", make_pdf(PAGES), "application/pdf")})
    assert c.post("/chat", json={"question": "photosynthesis converts light energy into glucose"}).json()["code"] == "question_too_long"
    assert c.post("/documents", files={"file": ("b.txt", b"a" * (1024 * 1024 + 5), "text/plain")}).status_code == 413


def test_question_frequency_limit(tmp_path, post):
    c = authed(create_app(make_settings(tmp_path, rate_llm_per_min=2)))
    post.queue = [resp(200, ok_body())]
    codes = [c.post("/chat", json=Q).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---------- citations ----------
def _src(ref, cid="abc123def456:p10:c18"):
    return Source(chunk_id=cid, document_id="d", document_name="Physics.pdf", page=10, excerpt="x", score=.9, ref=ref)


def test_clean_answer_repairs_and_removes_ids():
    s = number_sources([_src(None, "089b34b5a4c4:p10:c18"), _src(None, "089b34b5a4c4:p11:c19")])
    out = clean_answer("Force is mass times acceleration [089b34b5a4c4:p10:c18]. See also 089b34b5a4c4:p11:c19 and "
                       "[deadbeef0000:p1:c1] and [9] and [1, 9].", s)
    assert "089b34b5a4c4" not in out and "deadbeef" not in out
    assert "[1]" in out and "[2]" in out and "[9]" not in out and "[1, 9]" not in out


# ---------- production safety ----------
def test_production_config_validation(tmp_path):
    ok = dict(environment="production", jwt_secret="s" * 40, cors_origins="https://app.vercel.app/")
    assert make_settings(tmp_path, **ok).cors_list == ["https://app.vercel.app"]
    for bad in ({**ok, "jwt_secret": ""}, {**ok, "jwt_secret": "short"}, {**ok, "cors_origins": "*"},
                {**ok, "cors_origins": "http://app.vercel.app"}, {**ok, "cors_origins": ""}):
        with pytest.raises(RuntimeError):
            create_app(make_settings(tmp_path, **bad))
    create_app(make_settings(tmp_path, **ok))


def test_cors_allows_only_configured_origin(tmp_path):
    app = create_app(make_settings(tmp_path, cors_origins="https://app.vercel.app"))
    c = TestClient(app)
    good = c.options("/chat", headers={"Origin": "https://app.vercel.app", "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "authorization,x-llm-key"})
    bad = c.options("/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert good.headers.get("access-control-allow-origin") == "https://app.vercel.app"
    assert "access-control-allow-origin" not in bad.headers


def test_legacy_llm_env_still_configures_shared_key(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", llm_api_key="legacy-key-12345", llm_model="old-model")
    assert s.shared_gemini == ("legacy-key-12345", "old-model")
    s2 = Settings(_env_file=None, gemini_api_key="new-key-12345", llm_provider="gemini", llm_api_key="legacy")
    assert s2.shared_gemini[0] == "new-key-12345"
    assert Settings(_env_file=None).shared_gemini[0] == ""


def test_old_saved_personal_keys_are_wiped_at_startup(tmp_path):
    path = str(tmp_path / "old.db")
    db = Database(path)
    db.execute("INSERT INTO users (email, password_hash, llm_provider, llm_model, llm_key_enc) "
               "VALUES ('a@b.co','x','gemini','m','ENCRYPTED')")
    Database(path)   # restart
    row = db.query("SELECT llm_provider, llm_model, llm_key_enc FROM users")[0]
    assert row == {"llm_provider": None, "llm_model": None, "llm_key_enc": None}


def test_client_ip_uses_trusted_hop_not_spoofable_left_side(tmp_path):
    app = create_app(make_settings(tmp_path, trust_proxy_headers=True, trusted_proxy_hops=1, rate_auth_per_min=2))
    c = TestClient(app)
    body = {"email": "x@y.co", "password": "wrongpass1"}
    # attacker rotates the LEFT entry, but the proxy-appended right entry is constant -> still limited
    codes = [c.post("/auth/login", json=body, headers={"X-Forwarded-For": f"1.1.1.{i}, 9.9.9.9"}).status_code
             for i in range(3)]
    assert codes == [401, 401, 429]
    other = c.post("/auth/login", json=body, headers={"X-Forwarded-For": "1.1.1.1, 8.8.8.8"})
    assert other.status_code == 401                                   # a different real client is not limited


def test_error_shape_is_backward_compatible(ctx, post):
    app, c = ctx
    post.queue = [resp(503, {})]
    j = c.post("/chat", json=Q).json()
    assert isinstance(j["detail"], str) and j["code"]


def test_other_users_unaffected_by_exhaustion_message_but_isolated(tmp_path, post):
    app = create_app(make_settings(tmp_path))
    a, b = authed(app, "a@x.com"), authed(app, "b@x.com")
    a.post("/documents", files={"file": ("bio.pdf", make_pdf(PAGES), "application/pdf")})
    post.queue = [resp(200, ok_body())]
    assert b.post("/chat", json=Q).json()["status"] == "insufficient_evidence"   # isolation still holds
    assert a.post("/chat", json=Q).json()["status"] == "answered"


def test_health_diagnostics_are_secret_free(tmp_path):
    app = create_app(make_settings(tmp_path, ephemeral_storage_notice=True, trust_proxy_headers=True))
    h = TestClient(app).get("/health", headers={"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"}).json()
    assert h["status"] == "ok" and h["ephemeral_storage"] is True
    assert h["https_detected"] is True and h["client_ip"] == "203.0.113.9"
    assert SHARED not in json.dumps(h)
    assert TestClient(create_app(make_settings(tmp_path / "x"))).get("/health").json()["https_detected"] is False

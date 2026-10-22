import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import TopicStat
from app.services import learning, quiz
from .conftest import authed, login, make_pdf

PAGES = [
    "Photosynthesis converts light energy into glucose inside chloroplasts using chlorophyll.",
    "TCP is a reliable connection oriented transport protocol with acknowledgements and retransmission.",
]


class FakeLLM:
    configured = True

    def __init__(self, reply=None):
        self.reply, self.calls = reply, 0

    def generate(self, prompt):
        self.calls += 1
        if self.reply is not None:
            return self.reply(prompt) if callable(self.reply) else self.reply
        import re
        if "multiple-choice" not in prompt:
            return "Plain answer [1]."
        ids = re.findall(r"^\[(.+?)\]$", prompt, flags=re.M)
        qs = [{
            "question": f"Question number {i}?", "options": ["A1", "B2", "C3", "D4"],
            "answer_index": 1, "explanation": "Because B2.", "topic": "Biology" if i % 2 == 0 else "Networks",
            "difficulty": "easy", "source_chunk_ids": [ids[i % len(ids)]],
        } for i in range(4)]
        return "```json\n" + json.dumps({"questions": qs}) + "\n```"


@pytest.fixture
def app_client(settings):
    app = create_app(settings)
    app.state.llm = FakeLLM()
    c = authed(app)
    c.post("/documents", files={"file": ("n.pdf", make_pdf(PAGES), "application/pdf")})
    return c


def test_quiz_hides_answer_and_has_sources(app_client):
    r = app_client.post("/quizzes", json={"num_questions": 4})
    assert r.status_code == 201
    body = r.json()
    q = body["questions"][0]
    assert "answer_index" not in q and "explanation" not in q
    assert len(q["options"]) == 4 and q["sources"][0]["excerpt"] and q["sources"][0]["document_name"]
    assert "answer_index" not in app_client.get(f"/quizzes/{body['quiz_id']}").text


def test_scoring_deterministic_and_persisted(app_client):
    qid = app_client.post("/quizzes", json={"num_questions": 4}).json()["quiz_id"]
    answers = [{"question_id": 0, "selected_index": 1}, {"question_id": 1, "selected_index": 0},
               {"question_id": 2, "selected_index": 1}]  # q3 unanswered
    r1 = app_client.post(f"/quizzes/{qid}/submit", json={"answers": answers}).json()
    assert (r1["score"], r1["total"], r1["percent"]) == (2, 4, 50.0)
    assert r1["results"][0]["correct_index"] == 1 and r1["results"][3]["selected_index"] is None
    r2 = app_client.post(f"/quizzes/{qid}/submit", json={"answers": answers}).json()
    assert r2["score"] == r1["score"] and r2["attempt_id"] != r1["attempt_id"]
    hist = app_client.get("/attempts").json()
    assert len(hist) == 2 and hist[0]["score"] == 2


def test_submit_validation(app_client):
    qid = app_client.post("/quizzes", json={"num_questions": 4}).json()["quiz_id"]
    bad = lambda a: app_client.post(f"/quizzes/{qid}/submit", json={"answers": a}).status_code
    assert bad([{"question_id": 99, "selected_index": 0}]) == 422
    assert bad([{"question_id": 0, "selected_index": 7}]) == 422
    assert bad([{"question_id": 0, "selected_index": 0}, {"question_id": 0, "selected_index": 1}]) == 422
    assert app_client.post("/quizzes/999/submit", json={"answers": []}).status_code == 404


def test_invalid_llm_output_rejected(settings):
    app = create_app(settings)
    app.state.llm = FakeLLM("this is not json at all")
    c = authed(app)
    c.post("/documents", files={"file": ("n.pdf", make_pdf(PAGES), "application/pdf")})
    r = c.post("/quizzes", json={})
    assert r.status_code == 502 and app.state.llm.calls == 2  # one retry then fail


def test_parse_questions_drops_invalid():
    good = {"question": "What is it?", "options": ["a", "b", "c", "d"], "answer_index": 0,
            "explanation": "because", "topic": "T1", "difficulty": "easy", "source_chunk_ids": ["c1"]}
    cases = [
        {**good, "options": ["a", "b", "c"]},                 # 3 options
        {**good, "options": ["a", "a", "c", "d"]},            # duplicates
        {**good, "answer_index": 4},                          # key out of range
        {**good, "source_chunk_ids": ["made-up"]},            # fabricated citation
        {**good, "difficulty": "impossible"},
        {**good, "source_chunk_ids": []},
    ]
    valid, dropped = quiz.parse_questions(json.dumps({"questions": [good] + cases}), {"c1"})
    assert len(valid) == 1 and dropped == len(cases)


def test_quiz_missing_evidence_and_no_llm(settings):
    app = create_app(settings)
    app.state.llm = FakeLLM()
    c = authed(app)
    assert c.post("/quizzes", json={}).status_code == 422            # empty index
    app2 = login(create_app(settings))                            # no LLM configured
    assert app2.post("/quizzes", json={}).status_code == 503


def test_quiz_topic_without_matches(app_client):
    r = app_client.post("/quizzes", json={"topic": "medieval french poetry"})
    assert r.status_code == 422


def _answer_all(c, qid, wrong: bool):
    pick = 0 if wrong else 1
    return c.post(f"/quizzes/{qid}/submit",
                  json={"answers": [{"question_id": i, "selected_index": pick} for i in range(4)]})


def test_weak_topic_min_evidence_rule(app_client):
    app_client.post("/quizzes", json={"num_questions": 4})
    _answer_all(app_client, 1, wrong=True)
    w = app_client.get("/weak-topics").json()
    assert w["weak"] == [] and all(t["status"] == "insufficient_data" for t in w["topics"])  # 2 each < 5
    for _ in range(2):
        _answer_all(app_client, 1, wrong=True)
    w = app_client.get("/weak-topics").json()
    assert {t["topic"] for t in w["weak"]} == {"biology", "networks"}
    assert w["weak"][0]["accuracy"] == 0.0 and "at least 5" in w["rule"]


def test_good_performance_not_weak(app_client):
    app_client.post("/quizzes", json={"num_questions": 4})
    for _ in range(3):
        _answer_all(app_client, 1, wrong=False)
    assert app_client.get("/weak-topics").json()["weak"] == []


def test_plan_deterministic_and_bounded():
    weak = [TopicStat(topic="a", answered=10, correct=2, accuracy=0.2, status="weak"),
            TopicStat(topic="b", answered=10, correct=5, accuracy=0.5, status="weak")]
    p1 = learning.schedule(weak, 60, 3)
    assert p1 == learning.schedule(weak, 60, 3)
    for day in (1, 2, 3):
        assert sum(t.minutes for t in p1 if t.day == day) <= 60
    assert sum(t.minutes for t in p1 if t.topic == "a") > sum(t.minutes for t in p1 if t.topic == "b")
    assert max(t.day for t in p1) <= 3


def test_plan_api_and_exam_date(app_client):
    app_client.post("/quizzes", json={"num_questions": 4})
    for _ in range(3):
        _answer_all(app_client, 1, wrong=True)
    exam = (date.today() + timedelta(days=2)).isoformat()
    p = app_client.post("/revision-plan", json={"minutes_per_day": 50, "days": 10, "exam_date": exam}).json()
    assert p["days_planned"] == 2 and p["tasks"] and max(t["day"] for t in p["tasks"]) <= 2
    tid = p["tasks"][0]["task_id"]
    assert app_client.patch(f"/revision-tasks/{tid}", json={"status": "done"}).status_code == 200
    latest = app_client.get("/revision-plan").json()
    assert latest["tasks"][0]["status"] == "done"
    assert app_client.post("/revision-plan", json={"exam_date": "2020-01-01"}).status_code == 422
    assert app_client.post("/revision-plan", json={"exam_date": "bad"}).status_code == 422


def test_plan_without_weak_topics_is_explicit(client):
    p = client.post("/revision-plan", json={}).json()
    assert p["tasks"] == [] and "No weak topics" in p["note"]


def test_agent_routes(app_client):
    a = lambda m: app_client.post("/agent", json={"message": m})
    r = a("photosynthesis converts light energy into glucose using chlorophyll").json()
    assert (r["intent"], r["tool"]) == ("ask_notes", "search_notes") and r["result"]["sources"]
    assert a("which topics am I weak in?").json()["tool"] == "get_weak_topics"
    r = a("give me a quiz on photosynthesis converts light energy glucose chlorophyll").json()
    assert r["tool"] == "generate_quiz" and r["result"]["questions"]
    r = a("make a revision plan for 45 minutes for 3 days").json()
    assert r["tool"] == "create_revision_plan"


def test_agent_validates_args(app_client):
    r = app_client.post("/agent", json={"message": "revision plan 5 minutes"})
    assert r.status_code == 422   # minutes_per_day < 10


def test_tool_registry_is_whitelist():
    from app.services.tools import TOOLS
    assert set(TOOLS) == {"search_notes", "generate_quiz", "get_weak_topics", "create_revision_plan"}


def test_data_persists_across_restart(settings):
    app = create_app(settings); app.state.llm = FakeLLM()
    c = authed(app)
    c.post("/documents", files={"file": ("n.pdf", make_pdf(PAGES), "application/pdf")})
    qid = c.post("/quizzes", json={}).json()["quiz_id"]
    c.post(f"/quizzes/{qid}/submit", json={"answers": []})
    c2 = login(create_app(settings))
    assert len(c2.get("/attempts").json()) == 1

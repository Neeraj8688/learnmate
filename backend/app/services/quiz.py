import json
import re

from pydantic import ValidationError

from ..db import Database
from ..schemas import (PublicQuestion, PublicQuiz, QuestionResult, QuizQuestion, Source,
                       SubmitRequest, SubmitResponse)
from .retrieval import retrieve


class QuizError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def build_quiz_prompt(n: int, chunks: list[Source]) -> str:
    ctx = "\n\n".join(f"[{c.chunk_id}]\n{c.excerpt}" for c in chunks)
    return (
        f"Create {n} multiple-choice questions using ONLY the context below. "
        "Return ONLY JSON: {\"questions\":[{\"question\":str,\"options\":[4 distinct strings],"
        "\"answer_index\":0-3,\"explanation\":str,\"topic\":short string,"
        "\"difficulty\":\"easy|medium|hard\",\"source_chunk_ids\":[chunk ids from the context]}]}\n\n"
        f"CONTEXT:\n{ctx}"
    )


def parse_questions(raw: str, allowed_ids: set[str]) -> tuple[list[QuizQuestion], int]:
    """Parse + validate LLM output. Returns (valid questions, number dropped)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], 0
    items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return [], 0
    valid, dropped = [], 0
    for item in items:
        try:
            q = QuizQuestion.model_validate(item)
            if not set(q.source_chunk_ids) <= allowed_ids:  # citations must be real
                raise ValueError("unknown source chunk id")
            q.topic = q.topic.strip().lower()
            valid.append(q)
        except (ValidationError, ValueError, TypeError):
            dropped += 1
    return valid, dropped


def generate_quiz(st, topic, document_id, n) -> PublicQuiz:
    if not st.llm.configured:
        raise QuizError(503, "No AI is available. Connect your own Gemini API key to generate quizzes.")
    if topic:
        chunks = retrieve(st.store, topic, 8, st.settings.min_relevance)
        if document_id:
            chunks = [c for c in chunks if c.document_id == document_id]
    else:
        chunks = st.store.sample_chunks(document_id, 8)
    if not chunks:
        raise QuizError(422, "Not enough evidence in your notes to build a quiz.")
    by_id = {c.chunk_id: c for c in chunks}
    valid, dropped = [], 0
    for _attempt in range(2):  # one retry on unusable output
        raw = st.llm.generate(build_quiz_prompt(n, chunks))   # LLMError -> coded error response
        valid, dropped = parse_questions(raw, set(by_id))
        if valid:
            break
    if not valid:
        raise QuizError(502, "The LLM did not return a valid quiz. Please try again.")
    valid = valid[:n]
    stored = [
        {**q.model_dump(), "sources": [by_id[i].model_dump() for i in q.source_chunk_ids]}
        for q in valid
    ]
    quiz_id = st.db.execute("INSERT INTO quizzes (user_id, questions_json) VALUES (?,?)", (st.user_id, json.dumps(stored)))
    return public_quiz(quiz_id, stored, dropped)


def public_quiz(quiz_id: int, stored: list[dict], dropped: int = 0) -> PublicQuiz:
    return PublicQuiz(
        quiz_id=quiz_id, dropped_invalid=dropped,
        questions=[
            PublicQuestion(id=i, question=q["question"], options=q["options"], topic=q["topic"],
                           difficulty=q["difficulty"], sources=[Source(**s) for s in q["sources"]])
            for i, q in enumerate(stored)
        ],
    )


def load_quiz(db: Database, user_id: int, quiz_id: int) -> list[dict]:
    rows = db.query("SELECT questions_json FROM quizzes WHERE id=? AND user_id=?", (quiz_id, user_id))
    if not rows:
        raise QuizError(404, "Quiz not found.")
    return json.loads(rows[0]["questions_json"])


def score_quiz(stored: list[dict], answers: dict[int, int]) -> list[tuple[int, bool]]:
    """Deterministic scoring: unanswered counts as incorrect."""
    return [(i, answers.get(i) == q["answer_index"]) for i, q in enumerate(stored)]


def submit(db: Database, user_id: int, quiz_id: int, body: SubmitRequest) -> SubmitResponse:
    stored = load_quiz(db, user_id, quiz_id)
    answers: dict[int, int] = {}
    for a in body.answers:
        if not 0 <= a.question_id < len(stored):
            raise QuizError(422, f"Unknown question_id {a.question_id}.")
        if a.question_id in answers:
            raise QuizError(422, f"Duplicate answer for question_id {a.question_id}.")
        answers[a.question_id] = a.selected_index
    scored = score_quiz(stored, answers)
    score = sum(ok for _, ok in scored)
    attempt_id = db.execute(
        "INSERT INTO attempts (user_id, quiz_id, score, total) VALUES (?,?,?,?)", (user_id, quiz_id, score, len(stored))
    )
    for i, ok in scored:
        db.execute(
            "INSERT INTO attempt_answers (attempt_id, question_id, topic, selected_index, correct)"
            " VALUES (?,?,?,?,?)",
            (attempt_id, i, stored[i]["topic"], answers.get(i), int(ok)),
        )
    results = [
        QuestionResult(
            question_id=i, question=q["question"], options=q["options"],
            selected_index=answers.get(i), correct_index=q["answer_index"], correct=ok,
            explanation=q["explanation"], topic=q["topic"],
            sources=[Source(**s) for s in q["sources"]],
        )
        for (i, ok), q in zip(scored, stored)
    ]
    return SubmitResponse(attempt_id=attempt_id, quiz_id=quiz_id, score=score, total=len(stored),
                          percent=round(100 * score / len(stored), 1), results=results)

from fastapi import APIRouter, Depends, HTTPException

from ..deps import Ctx, get_ctx, rate_limit
from ..schemas import AttemptSummary, PublicQuiz, QuizRequest, SubmitRequest, SubmitResponse
from ..services import quiz

router = APIRouter()


def _wrap(fn, *a):
    try:
        return fn(*a)
    except quiz.QuizError as e:
        raise HTTPException(e.status, e.message)


@router.post("/quizzes", response_model=PublicQuiz, status_code=201, dependencies=[Depends(rate_limit("llm"))])
def create_quiz(body: QuizRequest, ctx: Ctx = Depends(get_ctx)):
    return _wrap(quiz.generate_quiz, ctx, body.topic, body.document_id, body.num_questions)


@router.get("/quizzes/{quiz_id}", response_model=PublicQuiz)
def get_quiz(quiz_id: int, ctx: Ctx = Depends(get_ctx)):
    stored = _wrap(quiz.load_quiz, ctx.db, ctx.user_id, quiz_id)
    return quiz.public_quiz(quiz_id, stored)  # answer key never exposed here


@router.post("/quizzes/{quiz_id}/submit", response_model=SubmitResponse)
def submit_quiz(quiz_id: int, body: SubmitRequest, ctx: Ctx = Depends(get_ctx)):
    return _wrap(quiz.submit, ctx.db, ctx.user_id, quiz_id, body)


@router.get("/attempts", response_model=list[AttemptSummary])
def attempts(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.query(
        "SELECT id AS attempt_id, quiz_id, score, total, created_at FROM attempts "
        "WHERE user_id=? ORDER BY id DESC", (ctx.user_id,))
    return [AttemptSummary(**r, percent=round(100 * r["score"] / r["total"], 1)) for r in rows]

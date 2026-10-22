from fastapi import APIRouter, Depends, HTTPException

from ..deps import Ctx, get_ctx, rate_limit
from ..llm import LLMError
from ..schemas import PlanRequest, PlanResponse, TaskStatusUpdate, WeakTopicsResponse
from ..services import learning

router = APIRouter()


@router.get("/weak-topics", response_model=WeakTopicsResponse)
def weak_topics(ctx: Ctx = Depends(get_ctx)):
    return learning.weak_topics(ctx.db, ctx.user_id, ctx.settings.min_attempts_per_topic,
                                ctx.settings.weak_threshold)


@router.post("/revision-plan", response_model=PlanResponse, dependencies=[Depends(rate_limit("llm"))])
def revision_plan(body: PlanRequest, ctx: Ctx = Depends(get_ctx)):
    weak = learning.weak_topics(ctx.db, ctx.user_id, ctx.settings.min_attempts_per_topic,
                                ctx.settings.weak_threshold).weak
    try:
        plan = learning.create_plan(ctx.db, ctx.user_id, weak, body.minutes_per_day, body.days, body.exam_date)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if body.explain and plan.tasks and ctx.llm.configured:  # LLM only explains; schedule is rule-based
        try:
            summary = "; ".join(f"day {t.day}: {t.topic} {t.minutes}min" for t in plan.tasks[:30])
            plan.explanation = ctx.llm.generate(
                "Briefly explain this study plan to a student in 3 sentences, adding nothing new: " + summary)
        except LLMError:  # includes budget exhaustion: the plan itself is still valid
            plan.explanation = None
    return plan


@router.get("/revision-plan", response_model=PlanResponse)
def get_plan(ctx: Ctx = Depends(get_ctx)):
    return learning.latest_plan(ctx.db, ctx.user_id)


@router.patch("/revision-tasks/{task_id}")
def update_task(task_id: int, body: TaskStatusUpdate, ctx: Ctx = Depends(get_ctx)):
    owned = ctx.db.query(
        "SELECT t.id FROM revision_tasks t JOIN revision_plans p ON p.id=t.plan_id "
        "WHERE t.id=? AND p.user_id=?", (task_id, ctx.user_id))
    if not owned:
        raise HTTPException(404, "Task not found.")
    ctx.db.execute("UPDATE revision_tasks SET status=? WHERE id=?", (body.status, task_id))
    return {"task_id": task_id, "status": body.status}

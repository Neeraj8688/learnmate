from datetime import date, datetime

from ..db import Database
from ..schemas import PlanResponse, PlanTask, TopicStat, WeakTopicsResponse

SESSION_MINUTES = 25


def weak_topics(db: Database, user_id: int, min_attempts: int, threshold: float) -> WeakTopicsResponse:
    """Rule: a topic is 'weak' only if answered >= min_attempts AND accuracy < threshold."""
    rows = db.query(
        "SELECT aa.topic AS topic, COUNT(*) AS answered, SUM(aa.correct) AS correct "
        "FROM attempt_answers aa JOIN attempts a ON a.id = aa.attempt_id "
        "WHERE a.user_id=? GROUP BY aa.topic ORDER BY aa.topic", (user_id,))
    topics = []
    for r in rows:
        acc = r["correct"] / r["answered"]
        if r["answered"] < min_attempts:
            status = "insufficient_data"
        else:
            status = "weak" if acc < threshold else "ok"
        topics.append(TopicStat(topic=r["topic"], answered=r["answered"], correct=r["correct"],
                                accuracy=round(acc, 3), status=status))
    weak = sorted((t for t in topics if t.status == "weak"), key=lambda t: (t.accuracy, t.topic))
    rule = (f"A topic is weak when at least {min_attempts} questions were answered on it "
            f"and accuracy is below {int(threshold * 100)}%.")
    return WeakTopicsResponse(rule=rule, topics=topics, weak=weak)


def resolve_days(days: int, exam_date: str | None, today: date | None = None) -> int:
    if not exam_date:
        return days
    try:
        exam = datetime.strptime(exam_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("exam_date must be YYYY-MM-DD")
    left = (exam - (today or date.today())).days
    if left < 1:
        raise ValueError("exam_date must be in the future")
    return min(days, left)


def schedule(weak: list[TopicStat], minutes_per_day: int, days: int) -> list[PlanTask]:
    """Deterministic: budget minutes per topic proportional to (1 - accuracy), then fill
    each day with <=25-minute sessions, cycling topics from weakest to strongest."""
    if not weak:
        return []
    total = minutes_per_day * days
    weights = [1 - t.accuracy + 0.05 for t in weak]  # +0.05 so 100%-of-threshold edge cases get time
    wsum = sum(weights)
    budget = [max(5, int(total * w / wsum) // 5 * 5) for w in weights]
    tasks: list[PlanTask] = []
    for day in range(1, days + 1):
        left = minutes_per_day
        while left > 0 and any(budget):
            progressed = False
            for i, t in enumerate(weak):
                m = min(SESSION_MINUTES, budget[i], left)
                if m <= 0:
                    continue
                tasks.append(PlanTask(day=day, topic=t.topic, minutes=m))
                budget[i] -= m
                left -= m
                progressed = True
                if left <= 0:
                    break
            if not progressed:
                break
    return tasks


def create_plan(db: Database, user_id: int, weak: list[TopicStat], minutes_per_day: int, days: int,
                exam_date: str | None = None) -> PlanResponse:
    days = resolve_days(days, exam_date)
    if not weak:
        return PlanResponse(plan_id=None, days_planned=0, tasks=[],
                            note="No weak topics identified yet (not enough quiz evidence, or "
                                 "performance is above the threshold). Take more quizzes first.")
    tasks = schedule(weak, minutes_per_day, days)
    note = f"Rule-based plan: {minutes_per_day} min/day over {days} day(s) for {len(weak)} weak topic(s)."
    plan_id = db.execute("INSERT INTO revision_plans (user_id, note) VALUES (?,?)", (user_id, note))
    for t in tasks:
        t.task_id = db.execute(
            "INSERT INTO revision_tasks (plan_id, day, topic, minutes) VALUES (?,?,?,?)",
            (plan_id, t.day, t.topic, t.minutes))
    return PlanResponse(plan_id=plan_id, note=note, days_planned=days, tasks=tasks)


def latest_plan(db: Database, user_id: int) -> PlanResponse:
    plans = db.query("SELECT id, note FROM revision_plans WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    if not plans:
        return PlanResponse(plan_id=None, note="No plan yet.", days_planned=0, tasks=[])
    rows = db.query("SELECT id, day, topic, minutes, status FROM revision_tasks "
                    "WHERE plan_id=? ORDER BY day, id", (plans[0]["id"],))
    tasks = [PlanTask(task_id=r["id"], day=r["day"], topic=r["topic"], minutes=r["minutes"],
                      status=r["status"]) for r in rows]
    return PlanResponse(plan_id=plans[0]["id"], note=plans[0]["note"],
                        days_planned=max((t.day for t in tasks), default=0), tasks=tasks)

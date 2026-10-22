"""Controlled tool workflow. Four whitelisted tools with validated arguments, dispatched by an
explicit keyword intent router (NOT provider-native tool calling). No shell or file access."""
import re

from pydantic import BaseModel, Field

from . import learning, quiz
from .answer import build_grounded_prompt, clean_answer, number_sources
from .retrieval import retrieve


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=1000)


class QuizArgs(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    num_questions: int = Field(default=5, ge=1, le=10)


class NoArgs(BaseModel):
    pass


class PlanArgs(BaseModel):
    minutes_per_day: int = Field(default=60, ge=10, le=600)
    days: int = Field(default=7, ge=1, le=30)


def search_notes(st, a: SearchArgs) -> dict:
    sources = number_sources(retrieve(st.store, a.query, st.settings.top_k, st.settings.min_relevance))
    if not sources:
        return {"status": "insufficient_evidence", "answer": "Not enough evidence in your notes.",
                "sources": []}
    if not st.llm.configured:
        return {"status": "llm_not_configured", "answer": "No AI available; connect your own Gemini API key. Showing passages.",
                "sources": [s.model_dump() for s in sources]}
    text = clean_answer(st.llm.generate(build_grounded_prompt(a.query, sources)), sources)  # LLMError -> coded error
    return {"status": "answered", "answer": text, "sources": [s.model_dump() for s in sources]}


def generate_quiz(st, a: QuizArgs) -> dict:
    return quiz.generate_quiz(st, a.topic, None, a.num_questions).model_dump()


def get_weak_topics(st, a: NoArgs) -> dict:
    return learning.weak_topics(st.db, st.user_id, st.settings.min_attempts_per_topic,
                                st.settings.weak_threshold).model_dump()


def create_revision_plan(st, a: PlanArgs) -> dict:
    w = learning.weak_topics(st.db, st.user_id, st.settings.min_attempts_per_topic, st.settings.weak_threshold)
    return learning.create_plan(st.db, st.user_id, w.weak, a.minutes_per_day, a.days).model_dump()


TOOLS = {
    "search_notes": (SearchArgs, search_notes),
    "generate_quiz": (QuizArgs, generate_quiz),
    "get_weak_topics": (NoArgs, get_weak_topics),
    "create_revision_plan": (PlanArgs, create_revision_plan),
}


def route(message: str) -> tuple[str, str, dict]:
    """Return (intent, tool_name, raw_args)."""
    m = message.lower()
    def nums(pat):
        found = re.search(pat, m)
        return int(found.group(1)) if found else None
    if re.search(r"\b(plan|schedule|revision|revise)\b", m):
        args = {k: v for k, v in {"minutes_per_day": nums(r"(\d+)\s*min"),
                                  "days": nums(r"(\d+)\s*days?")}.items() if v}
        return "revision_plan", "create_revision_plan", args
    if re.search(r"\b(weak|struggl\w*|worst|improve)\b", m):
        return "weak_topics", "get_weak_topics", {}
    if re.search(r"\b(quiz|test me|mcq|questions)\b", m):
        topic = re.sub(r"\b(make|create|generate|give|me|a|an|quiz|test|on|about|mcq|questions|of)\b",
                       " ", m)
        topic = " ".join(topic.split()) or None
        return "quiz", "generate_quiz", {"topic": topic}
    return "ask_notes", "search_notes", {"query": message}


def run_agent(st, message: str) -> tuple[str, str, dict]:
    intent, tool, raw = route(message)
    args_model, fn = TOOLS[tool]
    return intent, tool, fn(st, args_model.model_validate(raw))

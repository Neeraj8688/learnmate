from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page: Optional[int] = None
    excerpt: str
    score: float
    ref: Optional[int] = None   # 1-based number used by [n] citations in chat answers


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    pages: int
    chunks: int


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    chunks: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=20)


class SearchResponse(BaseModel):
    query: str
    results: list[Source]


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)  # real limit depends on key type (see config)


class ChatResponse(BaseModel):
    status: Literal["answered", "insufficient_evidence", "llm_not_configured"]
    answer: str
    sources: list[Source]


# ---------- Day 2: quiz, learning tools ----------
Difficulty = Literal["easy", "medium", "hard"]


class QuizQuestion(BaseModel):
    """Validated shape of one LLM-generated MCQ (internal; includes the answer key)."""
    question: str = Field(min_length=5)
    options: list[str]
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=3)
    topic: str = Field(min_length=2, max_length=80)
    difficulty: Difficulty
    source_chunk_ids: list[str] = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def four_unique_options(cls, v):
        v = [o.strip() for o in v]
        if len(v) != 4 or any(not o for o in v) or len(set(o.lower() for o in v)) != 4:
            raise ValueError("exactly 4 distinct non-empty options required")
        return v


class QuizRequest(BaseModel):
    topic: Optional[str] = Field(default=None, min_length=2, max_length=200)
    document_id: Optional[str] = None
    num_questions: int = Field(default=5, ge=1, le=10)


class PublicQuestion(BaseModel):  # answer key deliberately absent
    id: int
    question: str
    options: list[str]
    topic: str
    difficulty: Difficulty
    sources: list[Source]


class PublicQuiz(BaseModel):
    quiz_id: int
    questions: list[PublicQuestion]
    dropped_invalid: int = 0


class AnswerIn(BaseModel):
    question_id: int
    selected_index: int = Field(ge=0, le=3)


class SubmitRequest(BaseModel):
    answers: list[AnswerIn]


class QuestionResult(BaseModel):
    question_id: int
    question: str
    options: list[str]
    selected_index: Optional[int]
    correct_index: int
    correct: bool
    explanation: str
    topic: str
    sources: list[Source]


class SubmitResponse(BaseModel):
    attempt_id: int
    quiz_id: int
    score: int
    total: int
    percent: float
    results: list[QuestionResult]


class AttemptSummary(BaseModel):
    attempt_id: int
    quiz_id: int
    score: int
    total: int
    percent: float
    created_at: str


class TopicStat(BaseModel):
    topic: str
    answered: int
    correct: int
    accuracy: float
    status: Literal["weak", "ok", "insufficient_data"]


class WeakTopicsResponse(BaseModel):
    rule: str
    topics: list[TopicStat]
    weak: list[TopicStat]


class PlanRequest(BaseModel):
    minutes_per_day: int = Field(default=60, ge=10, le=600)
    days: int = Field(default=7, ge=1, le=30)
    exam_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    explain: bool = False


class PlanTask(BaseModel):
    task_id: Optional[int] = None
    day: int
    topic: str
    minutes: int
    status: str = "todo"


class PlanResponse(BaseModel):
    plan_id: Optional[int]
    note: str
    days_planned: int
    tasks: list[PlanTask]
    explanation: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: Literal["todo", "done"]


class AgentRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class AgentResponse(BaseModel):
    intent: str
    tool: str
    result: dict


# ---------- Day 3+: accounts, BYOK ----------
class AuthRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


class UsageInfo(BaseModel):
    server_calls_today: int
    server_calls_per_day_limit: int


class MeResponse(BaseModel):
    email: str
    server_llm_available: bool
    server_ai_status: Literal["ok", "user_quota_used", "site_quota_used", "not_configured"]
    usage: UsageInfo
    max_docs: int
    upload_max_mb: int

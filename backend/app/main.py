from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import Database
from .errors import AppError, app_error_handler, llm_error_handler
from .llm import LLMError, build_provider
from .ratelimit import RateLimiter, SharedQuota
from .routers import agent, auth, chat, documents, health, learning, quizzes
from .security import load_or_create_secret, new_jwt_secret
from .services.embeddings import build_embedder
from .services.vectorstore import VectorStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.validate_for_production()   # fail fast on unsafe production config
    app = FastAPI(title="LearnMate API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_list,
        allow_methods=["*"], allow_headers=["*"], expose_headers=["Retry-After"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(LLMError, llm_error_handler)
    app.state.settings = settings
    app.state.store = VectorStore(
        str(settings.persist_path), build_embedder(settings.embedding_backend, settings.embedding_model))
    app.state.db = Database(settings.sqlite_path)
    key, model = settings.shared_gemini
    app.state.llm = build_provider("gemini" if key else "none", key, model, settings.ai_timeout_seconds)  # shared demo key
    app.state.shared_quota = SharedQuota()
    app.state.limiter = RateLimiter()
    d = settings.data_dir
    app.state.jwt_secret = load_or_create_secret(settings.jwt_secret, d / ".jwt_secret", new_jwt_secret)
    for r in (health.router, auth.router, documents.router, chat.router, quizzes.router,
              learning.router, agent.router):
        app.include_router(r)
    return app

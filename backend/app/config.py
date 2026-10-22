from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"    # "production" turns on strict startup checks + HTTPS-only personal keys
    # Shared (demo) Gemini key: backend env only. Never exposed to the frontend, API or logs.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"   # per Google's model docs (checked 2026-10); verify before launch
    # Deprecated aliases kept so older .env files still work (GEMINI_* wins when set).
    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    ai_timeout_seconds: int = 45
    upload_max_mb: int = 10
    chroma_persist_directory: str = "./data/chroma"
    cors_origins: str = "http://localhost:5173"
    embedding_backend: str = "sentence-transformers"  # or "hash" (tests only)
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 4
    min_relevance: float = 0.30         # cosine similarity floor for answering
    sqlite_path: str = "./data/learnmate.db"
    min_attempts_per_topic: int = 5     # min answered questions before a topic can be called weak
    weak_threshold: float = 0.60        # topic accuracy below this (with enough evidence) = weak
    # --- accounts / security ---
    jwt_secret: str = ""                # empty -> generated once and stored next to the SQLite file
    jwt_days: int = 7
    allow_registration: bool = True
    trust_proxy_headers: bool = False   # true only behind a reverse proxy you control
    trusted_proxy_hops: int = 1         # proxies in front of the app; client IP = Nth entry from the right
    require_https_for_keys: bool | None = None  # None -> true in production, false otherwise
    ephemeral_storage_notice: bool = False  # true on hosts that wipe the disk (e.g. Render free): UI shows a demo-data notice
    # --- abuse / cost limits ---
    max_docs_per_user: int = 20
    max_chunks_per_doc: int = 3000
    daily_llm_calls_per_user: int = 30  # applies only when the SERVER key is used
    daily_llm_calls_global: int = 300   # server-key cap across all users
    rate_auth_per_min: int = 10         # per IP
    rate_llm_per_min: int = 15          # per user
    rate_upload_per_min: int = 10       # per user
    rate_general_per_min: int = 120     # per user
    demo_max_question_chars: int = 600  # request-length cap while using the SHARED key
    personal_max_question_chars: int = 2000   # cap when a visitor uses their own key
    quota_cooldown_minutes: int = 30    # after Gemini confirms the shared quota is exhausted, stop calling it
    quota_confirm_strikes: int = 3      # ambiguous 429s in a row before we treat the shared quota as exhausted

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def https_for_keys(self) -> bool:
        return self.is_production if self.require_https_for_keys is None else self.require_https_for_keys

    @property
    def shared_gemini(self) -> tuple[str, str]:
        """(key, model) for the shared demo key; GEMINI_API_KEY wins over the legacy LLM_* aliases."""
        if self.gemini_api_key:
            return self.gemini_api_key, self.gemini_model
        if self.llm_provider == "gemini" and self.llm_api_key:
            return self.llm_api_key, self.llm_model or self.gemini_model
        return "", self.gemini_model

    def validate_for_production(self) -> None:
        if not self.is_production:
            return
        problems = []
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to a random string of 32+ characters "
                            "(hosted filesystems are ephemeral, so it cannot be auto-generated)")
        origins = self.cors_list
        if not origins or "*" in origins:
            problems.append("CORS_ORIGINS must list your exact frontend origin(s); '*' is not allowed")
        elif any(not o.startswith("https://") for o in origins):
            problems.append("CORS_ORIGINS entries must be https:// origins in production")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))

    @property
    def data_dir(self) -> Path:
        return Path(self.sqlite_path).parent

    @property
    def cors_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def persist_path(self) -> Path:
        return Path(self.chroma_persist_directory)

"""Request context: authenticated user + per-user store + per-request AI gate + rate limits."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Request

from .db import Database
from .errors import AppError
from .llm import (InvalidAPIKey, LLMError, ProviderRateLimited, QuotaExceeded, ServerAIMisconfigured,
                  BudgetExceeded, build_provider)
from .security import decode_token
from .services import accounts
from .services.vectorstore import ScopedStore

log = logging.getLogger("learnmate")


def client_ip(request: Request) -> str:
    st = request.app.state.settings
    if st.trust_proxy_headers:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if parts:
            # With N trusted proxies the real client is the Nth entry from the RIGHT; anything to the
            # left was supplied by the client and can be forged.
            return parts[-min(st.trusted_proxy_hops, len(parts))]
    return request.client.host if request.client else "unknown"


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    st = request.app.state.settings
    return st.trust_proxy_headers and request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


class LLMGate:
    """Wraps the chosen provider and classifies outcomes.

    - Shared key: per-user and site-wide DEMO budgets apply, and a confirmed Gemini quota exhaustion
      switches the shared key off for a cooldown.
    - Personal key: never counted against the demo budget, and failures are reported as the visitor's
      own (never silently retried on the shared key)."""

    def __init__(self, provider, st, user_id: int, own_key: bool):
        self.provider, self.st, self.db, self.settings = provider, st, st.db, st.settings
        self.user_id, self.own_key = user_id, own_key
        self.configured = provider.configured

    def generate(self, prompt: str) -> str:
        day = datetime.now(timezone.utc).date().isoformat()
        reserved = False
        if not self.own_key:
            if self.st.shared_quota.exhausted():
                raise QuotaExceeded("shared")
            hit = self.db.reserve_llm_call(self.user_id, day, self.settings.daily_llm_calls_per_user,
                                           self.settings.daily_llm_calls_global)
            if hit:
                raise BudgetExceeded(
                    "You've used today's demo allowance. Connect your own Gemini API key to keep going."
                    if hit == "user" else
                    "The site's shared demo allowance for today is used up. Connect your own Gemini API "
                    "key to keep going.")
            reserved = True
        try:
            out = self.provider.generate(prompt)
        except LLMError as exc:
            if reserved:
                self.db.release_llm_call(self.user_id, day)   # no answer produced: don't charge the allowance
            raise self._attribute(exc) from None
        if not self.own_key:
            self.st.shared_quota.success()
        return out

    def _attribute(self, exc: LLMError) -> LLMError:
        """Decide whose problem this is. Never leaks provider text or keys."""
        if isinstance(exc, QuotaExceeded):
            if self.own_key:
                return QuotaExceeded("personal")
            self.st.shared_quota.mark_exhausted(self.settings.quota_cooldown_minutes)
            log.warning("Shared Gemini quota confirmed exhausted; pausing shared key for %s min",
                        self.settings.quota_cooldown_minutes)
            return QuotaExceeded("shared")
        if isinstance(exc, ProviderRateLimited) and exc.ambiguous and not self.own_key:
            if self.st.shared_quota.strike(self.settings.quota_confirm_strikes):
                self.st.shared_quota.mark_exhausted(self.settings.quota_cooldown_minutes)
                log.warning("Repeated ambiguous 429s: treating shared Gemini quota as exhausted")
                return QuotaExceeded("shared")
            return exc
        if isinstance(exc, InvalidAPIKey) and not self.own_key:
            log.error("The SHARED Gemini key was rejected by Google. Check GEMINI_API_KEY.")
            return ServerAIMisconfigured()
        return exc


@dataclass
class Ctx:
    user_id: int
    email: str
    settings: object
    db: Database
    store: ScopedStore
    llm: LLMGate


def current_user(request: Request) -> dict:
    st = request.app.state
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    uid = decode_token(st.jwt_secret, token) if token else None
    user = accounts.get_by_id(st.db, uid) if uid else None
    if not user:
        raise AppError(401, "not_authenticated", "Not authenticated.", {"WWW-Authenticate": "Bearer"})
    st.limiter.check(f"general:{user['id']}", st.settings.rate_general_per_min)
    return user


def get_ctx(request: Request, user: dict = Depends(current_user)) -> Ctx:
    st = request.app.state
    cfg = st.settings
    key = (request.headers.get("x-llm-key") or "").strip()
    if key:
        # Personal key: lives only in this request (the browser keeps it for the session). Never stored.
        if cfg.https_for_keys and not is_https(request):
            raise AppError(400, "https_required", "Personal API keys are only accepted over HTTPS.")
        prov = (request.headers.get("x-llm-provider") or "gemini").strip()
        if prov != "gemini" or not 8 <= len(key) <= 300:
            raise AppError(422, "invalid_key_format", "Invalid personal API key settings.")
        provider, own = build_provider("gemini", key, cfg.shared_gemini[1], cfg.ai_timeout_seconds), True
    else:
        provider, own = st.llm, False
    return Ctx(user_id=user["id"], email=user["email"], settings=cfg, db=st.db,
               store=ScopedStore(st.store, user["id"]), llm=LLMGate(provider, st, user["id"], own))


def rate_limit(kind: str):
    """Dependency factory: per-user limit for 'llm' or 'upload' actions."""
    def dep(request: Request, user: dict = Depends(current_user)):
        st = request.app.state
        limit = {"llm": st.settings.rate_llm_per_min, "upload": st.settings.rate_upload_per_min}[kind]
        st.limiter.check(f"{kind}:{user['id']}", limit)
    return dep


def auth_rate_limit(request: Request):
    st = request.app.state
    st.limiter.check(f"auth:{client_ip(request)}", st.settings.rate_auth_per_min)


def check_question_length(ctx: Ctx, text: str) -> None:
    cap = ctx.settings.personal_max_question_chars if ctx.llm.own_key else ctx.settings.demo_max_question_chars
    if len(text) > cap:
        raise AppError(422, "question_too_long",
                       f"Questions are limited to {cap} characters{'' if ctx.llm.own_key else ' in demo mode'}. "
                       f"Yours is {len(text)}.")

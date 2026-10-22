from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import Ctx, auth_rate_limit, current_user, get_ctx, rate_limit
from ..errors import llm_error_payload
from ..llm import LLMError
from ..schemas import AuthRequest, MeResponse, TokenResponse, UsageInfo
from ..security import hash_password, make_token, verify_password
from ..services import accounts

router = APIRouter()


def _token(st, user_id: int, email: str) -> TokenResponse:
    return TokenResponse(access_token=make_token(st.jwt_secret, user_id, st.settings.jwt_days), email=email)


@router.post("/auth/register", response_model=TokenResponse, status_code=201,
             dependencies=[Depends(auth_rate_limit)])
def register(body: AuthRequest, request: Request):
    st = request.app.state
    if not st.settings.allow_registration:
        raise HTTPException(403, "Registration is closed.")
    email = accounts.normalize_email(body.email)
    if not accounts.valid_email(email):
        raise HTTPException(422, "Enter a valid email address.")
    if accounts.get_by_email(st.db, email):
        raise HTTPException(409, "An account with this email already exists.")
    uid = accounts.create_user(st.db, email, hash_password(body.password))
    return _token(st, uid, email)


@router.post("/auth/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
def login(body: AuthRequest, request: Request):
    st = request.app.state
    email = accounts.normalize_email(body.email)
    user = accounts.get_by_email(st.db, email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    return _token(st, user["id"], email)


@router.get("/me", response_model=MeResponse)
def me(request: Request, user: dict = Depends(current_user)):
    st = request.app.state
    day = datetime.now(timezone.utc).date().isoformat()
    rows = st.db.query("SELECT calls FROM llm_usage WHERE user_id=? AND day=?", (user["id"], day))
    used = rows[0]["calls"] if rows else 0
    site = st.db.query("SELECT COALESCE(SUM(calls),0) AS n FROM llm_usage WHERE day=?", (day,))[0]["n"]
    if not st.llm.configured:
        ai_status = "not_configured"
    elif st.shared_quota.exhausted() or site >= st.settings.daily_llm_calls_global:
        ai_status = "site_quota_used"
    elif used >= st.settings.daily_llm_calls_per_user:
        ai_status = "user_quota_used"
    else:
        ai_status = "ok"
    return MeResponse(
        email=user["email"], server_llm_available=st.llm.configured, server_ai_status=ai_status,
        usage=UsageInfo(server_calls_today=used,
                        server_calls_per_day_limit=st.settings.daily_llm_calls_per_user),
        max_docs=st.settings.max_docs_per_user, upload_max_mb=st.settings.upload_max_mb)


@router.post("/llm/check", dependencies=[Depends(rate_limit("llm"))])
def check_llm(ctx: Ctx = Depends(get_ctx)):
    """Verify whichever AI source applies to this request (personal key header, else the shared key)."""
    if not ctx.llm.configured:
        return {"ok": False, "code": "not_configured", "error": "No AI source is configured."}
    try:
        ctx.llm.generate("Reply with the single word OK.")
        return {"ok": True, "source": "personal" if ctx.llm.own_key else "shared"}
    except LLMError as exc:
        _, code, msg, _ = llm_error_payload(exc)
        return {"ok": False, "code": code, "error": msg}


@router.delete("/me")
def delete_account(request: Request, ctx: Ctx = Depends(get_ctx)):
    """Permanently delete the account, its notes, vectors, quizzes and plans."""
    ctx.store.delete_all()
    ctx.db.delete_user_data(ctx.user_id)
    return {"deleted": True}

"""One place that turns AI/app failures into JSON: {"detail": <message>, "code": <stable code>}.
`detail` stays a plain string, so older clients that only read `detail` keep working."""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from .llm import LLMError, ProviderRateLimited, ProviderUnavailable, QuotaExceeded

log = logging.getLogger("learnmate")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def _json(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": message, "code": code}, status_code=status, headers=headers or {})


async def app_error_handler(request: Request, exc: AppError):
    return _json(exc.status, exc.code, exc.message, exc.headers)


def llm_error_payload(exc: LLMError) -> tuple[int, str, str, dict]:
    headers = {}
    if isinstance(exc, ProviderRateLimited):
        headers["Retry-After"] = str(exc.retry_after)
    elif isinstance(exc, ProviderUnavailable):
        headers["Retry-After"] = "5"
    return exc.status, exc.code, str(exc), headers


async def llm_error_handler(request: Request, exc: LLMError):
    status, code, msg, headers = llm_error_payload(exc)
    return _json(status, code, msg, headers)

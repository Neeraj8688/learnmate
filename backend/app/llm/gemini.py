"""Gemini adapter (REST). Provider-specific code lives only here.

Error handling is deliberately classified (see llm/base.py): confirmed quota, temporary rate limit,
invalid key, temporary 503, network failure. Messages never include the API key or the raw body.

Per Google's docs (checked 2026-10), 429 is RESOURCE_EXHAUSTED and 503 is UNAVAILABLE, but the 429
body format is not documented in detail, so the quota/rate-limit split is a best-effort parse of the
standard google.rpc error details and is covered by mocked tests only.
"""
import json
import time

import httpx

from .base import (InvalidAPIKey, LLMError, ProviderNetworkError, ProviderRateLimited,
                   ProviderUnavailable, QuotaExceeded)

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _squash(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def classify_429(body_text: str) -> LLMError:
    """Confirmed daily quota -> QuotaExceeded; per-minute style -> ProviderRateLimited;
    anything else is ambiguous (the gate escalates repeated ambiguous 429s)."""
    flat = _squash(body_text)
    retry = 10
    try:
        for d in json.loads(body_text).get("error", {}).get("details", []):
            delay = str(d.get("retryDelay", ""))
            if delay.endswith("s") and delay[:-1].replace(".", "", 1).isdigit():
                retry = max(1, min(120, int(float(delay[:-1]))))
    except (ValueError, AttributeError, TypeError):
        pass
    if "perday" in flat or "daily" in flat or "requestsperday" in flat:
        return QuotaExceeded()
    if "perminute" in flat or "retrydelay" in flat:
        return ProviderRateLimited(retry_after=retry)
    return ProviderRateLimited(retry_after=retry, ambiguous=True)


def classify_response(status: int, body_text: str) -> LLMError:
    low = body_text.lower()
    if status == 429:
        return classify_429(body_text)
    if status in (500, 502, 503, 504, 408):
        return ProviderUnavailable()
    if status in (401, 403) or (status == 400 and ("api key" in low or "api_key" in low)):
        return InvalidAPIKey()
    if status == 404:
        return LLMError("The configured Gemini model was not found. Check the model name.")
    return LLMError("The AI provider rejected the request.")


class GeminiProvider:
    def __init__(self, api_key: str, model: str, timeout: float = 45.0, retries: int = 1):
        self.api_key, self.model, self.timeout, self.retries = api_key, model, timeout, retries
        self.configured = bool(api_key and model)

    def _once(self, prompt: str) -> str:
        try:
            r = httpx.post(
                _URL.format(model=self.model),
                headers={"x-goog-api-key": self.api_key},   # header, never in the URL (URLs get logged)
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=self.timeout,
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError):
            raise ProviderNetworkError() from None          # `from None`: drop chained exception text
        if r.status_code >= 400:
            raise classify_response(r.status_code, r.text) from None
        try:
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("The AI returned no usable answer (it may have been blocked). "
                           "Try rephrasing your question.") from None

    def generate(self, prompt: str) -> str:
        for attempt in range(self.retries + 1):
            try:
                return self._once(prompt)
            except (ProviderUnavailable, ProviderNetworkError):
                if attempt >= self.retries:
                    raise
                time.sleep(1.0 * (attempt + 1))   # short backoff, one retry only
        raise ProviderUnavailable()  # pragma: no cover

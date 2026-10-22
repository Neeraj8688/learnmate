from typing import Protocol


class LLMError(RuntimeError):
    """Base for every AI-provider problem. Subclasses carry a stable machine-readable `code`
    and an HTTP status so the API and UI can treat each failure differently."""
    code = "provider_error"
    status = 502
    public_message = "The AI provider returned an error. Please try again."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.public_message)


class BudgetExceeded(LLMError):
    """The configured per-user or site-wide DEMO allowance for the shared key is used up."""
    code = "demo_limit_reached"
    status = 429
    public_message = ("You've reached today's demo usage limit. Connect your own Gemini API key "
                      "to keep going.")


class QuotaExceeded(LLMError):
    """Gemini confirmed a quota limit. `scope` says whose key hit it: 'shared' or 'personal'."""
    status = 429

    def __init__(self, scope: str = "shared"):
        self.scope = scope
        self.code = f"{scope}_quota_exhausted"
        super().__init__(
            "The shared demo quota has been reached. Connect your own Gemini API key to continue."
            if scope == "shared" else
            "Your Gemini API key has reached its quota. Try again later or use a different key.")


class ProviderRateLimited(LLMError):
    """Temporary per-minute style throttling (not a confirmed quota exhaustion)."""
    code = "provider_rate_limited"
    status = 429
    public_message = "The AI service is busy right now. Please wait a moment and try again."

    def __init__(self, retry_after: int = 10, ambiguous: bool = False):
        self.retry_after, self.ambiguous = retry_after, ambiguous
        super().__init__()


class InvalidAPIKey(LLMError):
    code = "invalid_api_key"
    status = 400
    public_message = "Gemini rejected this API key. Check that it is correct and enabled."


class ServerAIMisconfigured(LLMError):
    """The SHARED key was rejected: an operator problem, never blamed on the visitor."""
    code = "server_ai_misconfigured"
    status = 503
    public_message = "The demo AI is temporarily unavailable. Please try again later."


class ProviderUnavailable(LLMError):
    code = "provider_unavailable"
    status = 503
    public_message = "The AI service is temporarily unavailable (HTTP 503). Please retry in a moment."


class ProviderNetworkError(LLMError):
    code = "provider_network_error"
    status = 502
    public_message = "Could not reach the AI service. Check your connection and try again."


class LLMProvider(Protocol):
    configured: bool

    def generate(self, prompt: str) -> str: ...

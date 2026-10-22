from .base import (BudgetExceeded, InvalidAPIKey, LLMError, LLMProvider, ProviderNetworkError,
                   ProviderRateLimited, ProviderUnavailable, QuotaExceeded, ServerAIMisconfigured)
from .gemini import GeminiProvider
from .none import NoProvider


def build_provider(name: str, api_key: str, model: str, timeout: float = 45.0) -> LLMProvider:
    """Only Gemini is supported. Anything else yields an unconfigured provider."""
    if name == "gemini":
        return GeminiProvider(api_key, model, timeout=timeout)
    return NoProvider()


__all__ = ["BudgetExceeded", "InvalidAPIKey", "LLMError", "LLMProvider", "ProviderNetworkError",
           "ProviderRateLimited", "ProviderUnavailable", "QuotaExceeded", "ServerAIMisconfigured",
           "build_provider"]

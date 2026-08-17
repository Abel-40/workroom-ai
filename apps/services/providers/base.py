from abc import ABC, abstractmethod


class ProviderError(Exception):
    """Base for provider-originated failures. See AI_SERVICE_SPEC.md #5."""

    retryable = False


class TransientProviderError(ProviderError):
    """Timeout, rate limit, temporary outage -- safe for the caller to retry."""

    retryable = True


class PermanentProviderError(ProviderError):
    """Bad config, unsupported model, malformed request -- retrying won't help."""

    retryable = False


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return the raw text of a JSON completion for the given prompts."""
        raise NotImplementedError

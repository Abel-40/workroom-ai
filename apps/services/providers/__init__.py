from apps.core.config import settings

from .base import AIProvider, PermanentProviderError, ProviderError, TransientProviderError
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider

_PROVIDERS = {
    'gemini': GeminiProvider,
    'deepseek': DeepSeekProvider,
}


def get_provider(name: str = None) -> AIProvider:
    provider_name = (name or settings.AI_PROVIDER).lower()
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise PermanentProviderError(f"Unknown AI provider '{provider_name}'.")
    return provider_cls()


__all__ = [
    'AIProvider',
    'ProviderError',
    'TransientProviderError',
    'PermanentProviderError',
    'get_provider',
]

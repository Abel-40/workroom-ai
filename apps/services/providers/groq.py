"""Groq's compound systems (groq/compound, groq/compound-mini) have built-in
web search (via Tavily) and decide per-query whether to invoke it -- no
separate search-API integration needed here.

GroqAssistantProvider deliberately does NOT implement the AIProvider ABC
(base.py): AIProvider.complete_json is a forced-JSON-mode contract, and a
compound-mini call is neither JSON-mode nor side-effect-free (it may invoke
a tool). Reusing that method name for something that doesn't honor it would
be a false abstraction, not code reuse. This class is only ever constructed
directly by the assistant service, never through providers.get_provider().
"""

import httpx

from apps.core.config import settings

from .base import PermanentProviderError, TransientProviderError

GROQ_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'


class GroqAssistantProvider:
    name = 'groq'

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GROQ_API_KEY1
        self.model = model or settings.GROQ_MODEL
        if not self.api_key:
            raise PermanentProviderError('GROQ_API_KEY1 is not configured.')

    async def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            # No response_format here: compound models' tool-use loop
            # (deciding whether to search) doesn't reliably combine with
            # forced JSON mode. The guardrail refusal signal is a plain-text
            # sentinel (OUT_OF_SCOPE:) instead -- see
            # apps/services/assistant_services.py.
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(GROQ_ENDPOINT, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise TransientProviderError('Groq request timed out.') from exc
        except httpx.HTTPError as exc:
            raise TransientProviderError(f'Groq request failed: {exc}') from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError(f'Groq returned {response.status_code}.')
        if response.status_code >= 400:
            raise PermanentProviderError(f'Groq rejected the request: {response.status_code}.')

        data = response.json()
        try:
            return data['choices'][0]['message']['content']
        except (KeyError, IndexError) as exc:
            raise PermanentProviderError('Groq response did not contain completion text.') from exc


def get_groq_assistant_provider() -> GroqAssistantProvider:
    return GroqAssistantProvider()

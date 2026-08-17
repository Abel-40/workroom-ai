
import httpx

from apps.core.config import settings

from .base import AIProvider, PermanentProviderError, TransientProviderError

DEEPSEEK_ENDPOINT = 'https://api.deepseek.com/chat/completions'


class DeepSeekProvider(AIProvider):
    name = 'deepseek'

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.DEEPSEEK_API_KEY1
        self.model = model or settings.DEEPSEEK_MODEL
        if not self.api_key:
            raise PermanentProviderError('DEEPSEEK_API_KEY1 is not configured.')

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.2,
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(DEEPSEEK_ENDPOINT, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise TransientProviderError('DeepSeek request timed out.') from exc
        except httpx.HTTPError as exc:
            raise TransientProviderError(f'DeepSeek request failed: {exc}') from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError(f'DeepSeek returned {response.status_code}.')
        if response.status_code >= 400:
            raise PermanentProviderError(f'DeepSeek rejected the request: {response.status_code}.')

        data = response.json()
        try:
            return data['choices'][0]['message']['content']
        except (KeyError, IndexError) as exc:
            raise PermanentProviderError('DeepSeek response did not contain completion text.') from exc

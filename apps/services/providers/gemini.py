
import httpx

from apps.core.config import settings

from .base import AIProvider, PermanentProviderError, TransientProviderError

GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'


class GeminiProvider(AIProvider):
    name = 'gemini'

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY1
        self.model = model or settings.GEMINI_MODEL
        if not self.api_key:
            raise PermanentProviderError('GEMINI_API_KEY1 is not configured.')

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        url = GEMINI_ENDPOINT.format(model=self.model)
        body = {
            'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
            'systemInstruction': {'parts': [{'text': system_prompt}]},
            'generationConfig': {
                'responseMimeType': 'application/json',
                'temperature': 0.2,
                # Extended "thinking" adds significant latency for this kind
                # of structured-output task and made longer prompts prone to
                # timing out / getting overloaded in testing; not needed here.
                'thinkingConfig': {'thinkingBudget': 0},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(url, params={'key': self.api_key}, json=body)
        except httpx.TimeoutException as exc:
            raise TransientProviderError('Gemini request timed out.') from exc
        except httpx.HTTPError as exc:
            raise TransientProviderError(f'Gemini request failed: {exc}') from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError(f'Gemini returned {response.status_code}.')
        if response.status_code >= 400:
            raise PermanentProviderError(f'Gemini rejected the request: {response.status_code}.')

        data = response.json()
        try:
            return data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError) as exc:
            raise PermanentProviderError('Gemini response did not contain completion text.') from exc

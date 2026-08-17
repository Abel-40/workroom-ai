from unittest.mock import patch

import httpx
import pytest
import respx

from apps.services.providers.base import PermanentProviderError, TransientProviderError
from apps.services.providers.groq import GROQ_ENDPOINT, GroqAssistantProvider


def test_missing_api_key_raises_permanent_error_at_construction():
    # api_key='' alone isn't enough to test this: the constructor falls back
    # to settings.GROQ_API_KEY1, which is genuinely populated in this repo's
    # .env -- so settings itself must be patched empty too.
    with patch('apps.services.providers.groq.settings.GROQ_API_KEY1', ''):
        with pytest.raises(PermanentProviderError):
            GroqAssistantProvider(api_key='', model='groq/compound-mini')


@pytest.mark.asyncio
@respx.mock
async def test_successful_completion_returns_content():
    respx.post(GROQ_ENDPOINT).mock(
        return_value=httpx.Response(200, json={'choices': [{'message': {'content': 'Here is your answer.'}}]}),
    )
    provider = GroqAssistantProvider(api_key='fake-key', model='groq/compound-mini')
    result = await provider.complete_text(system_prompt='sys', user_prompt='user')
    assert result == 'Here is your answer.'


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_raises_transient_error():
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(429, json={}))
    provider = GroqAssistantProvider(api_key='fake-key', model='groq/compound-mini')
    with pytest.raises(TransientProviderError):
        await provider.complete_text(system_prompt='sys', user_prompt='user')


@pytest.mark.asyncio
@respx.mock
async def test_server_error_raises_transient_error():
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(503, json={}))
    provider = GroqAssistantProvider(api_key='fake-key', model='groq/compound-mini')
    with pytest.raises(TransientProviderError):
        await provider.complete_text(system_prompt='sys', user_prompt='user')


@pytest.mark.asyncio
@respx.mock
async def test_other_client_error_raises_permanent_error():
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(400, json={}))
    provider = GroqAssistantProvider(api_key='fake-key', model='groq/compound-mini')
    with pytest.raises(PermanentProviderError):
        await provider.complete_text(system_prompt='sys', user_prompt='user')


@pytest.mark.asyncio
@respx.mock
async def test_missing_content_raises_permanent_error():
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(200, json={'choices': [{}]}))
    provider = GroqAssistantProvider(api_key='fake-key', model='groq/compound-mini')
    with pytest.raises(PermanentProviderError):
        await provider.complete_text(system_prompt='sys', user_prompt='user')

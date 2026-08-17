import uuid

import pytest

from apps.schemas.assistant_schemas import AIAssistantRequest
from apps.services.assistant_services import AssistantAnswerError, generate_assistant_answer


class StubGroqProvider:
    """Does not implement AIProvider -- GroqAssistantProvider deliberately
    doesn't either (see apps/services/providers/groq.py)."""

    name = 'groq'
    model = 'groq/compound-mini'

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


def make_request(**overrides):
    defaults = dict(
        query_id=uuid.uuid4(), project_id=uuid.uuid4(), question='What tasks are still To Do?',
        project_title='Support platform', project_description='A SaaS support platform.',
    )
    defaults.update(overrides)
    return AIAssistantRequest(**defaults)


@pytest.mark.asyncio
async def test_answer_is_returned_as_is():
    answer = await generate_assistant_answer(make_request(), provider=StubGroqProvider('You have 2 tasks left.'))
    assert answer == 'You have 2 tasks left.'


@pytest.mark.asyncio
async def test_out_of_scope_sentinel_is_not_interpreted_here():
    """FastAPI must NOT strip or interpret the OUT_OF_SCOPE: sentinel --
    Django owns that parsing (ai_agent/tasks_assistant.py), so this service
    must pass it through unmodified."""
    raw = 'OUT_OF_SCOPE: This is unrelated to the project.'
    answer = await generate_assistant_answer(make_request(), provider=StubGroqProvider(raw))
    assert answer == raw


@pytest.mark.asyncio
async def test_empty_answer_raises_error():
    with pytest.raises(AssistantAnswerError):
        await generate_assistant_answer(make_request(), provider=StubGroqProvider('   '))


@pytest.mark.asyncio
async def test_prompt_includes_reference_and_document_context():
    captured = {}

    class CapturingProvider(StubGroqProvider):
        async def complete_text(self, *, system_prompt, user_prompt):
            captured['user_prompt'] = user_prompt
            return 'ok'

    request = make_request(
        task_titles=['Set up CI', 'Write docs'],
        reference_url='https://example.com/spec',
        reference_url_content='The spec says to use PostgreSQL.',
        document_excerpts=['Internal note: deadline is Friday.'],
    )
    await generate_assistant_answer(request, provider=CapturingProvider('ok'))
    assert 'Set up CI' in captured['user_prompt']
    assert 'PostgreSQL' in captured['user_prompt']
    assert 'deadline is Friday' in captured['user_prompt']

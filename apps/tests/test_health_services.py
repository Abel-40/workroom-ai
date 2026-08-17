import json
import uuid

import pytest

from apps.schemas.health_schemas import AIProjectHealthRequest
from apps.services.health_services import HealthValidationError, generate_health_summary
from apps.services.providers.base import AIProvider


class StubProvider(AIProvider):
    name = 'stub'

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


def make_request(**stat_overrides):
    stats = dict(
        total_tasks=10, completed_tasks=4, in_progress_tasks=3, todo_tasks=2,
        in_review_tasks=1, overdue_tasks=2, unassigned_tasks=3, completion_percent=40.0,
    )
    stats.update(stat_overrides)
    return AIProjectHealthRequest(
        summary_id=uuid.uuid4(), project_id=uuid.uuid4(), project_title='Support platform', stats=stats,
    )


@pytest.mark.asyncio
async def test_valid_summary_is_accepted():
    raw = json.dumps({'summary': 'On track, minor overdue work.', 'risk_level': 'low'})
    result = await generate_health_summary(make_request(), provider=StubProvider(raw))
    assert result.risk_level == 'low'
    assert 'overdue' in result.summary


@pytest.mark.asyncio
async def test_invalid_risk_level_is_rejected():
    raw = json.dumps({'summary': 'Some summary.', 'risk_level': 'catastrophic'})
    with pytest.raises(HealthValidationError):
        await generate_health_summary(make_request(), provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_non_json_output_is_rejected():
    with pytest.raises(HealthValidationError):
        await generate_health_summary(make_request(), provider=StubProvider('Sure, here is a summary...'))


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_still_parsed():
    raw = '```json\n' + json.dumps({'summary': 'ok', 'risk_level': 'medium'}) + '\n```'
    result = await generate_health_summary(make_request(), provider=StubProvider(raw))
    assert result.risk_level == 'medium'

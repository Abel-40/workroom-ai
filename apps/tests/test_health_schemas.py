import uuid

import pytest
from pydantic import ValidationError

from apps.schemas.health_schemas import AIProjectHealthRequest, AIProjectHealthSummary, ProjectStatsRef


def make_stats(**overrides):
    defaults = dict(
        total_tasks=10, completed_tasks=4, in_progress_tasks=3, todo_tasks=2,
        in_review_tasks=1, overdue_tasks=2, unassigned_tasks=3, completion_percent=40.0,
    )
    defaults.update(overrides)
    return ProjectStatsRef(**defaults)


def test_valid_request_is_accepted():
    request = AIProjectHealthRequest(
        summary_id=uuid.uuid4(), project_id=uuid.uuid4(), project_title='Support platform', stats=make_stats(),
    )
    assert request.stats.unassigned_tasks == 3


def test_summary_requires_valid_risk_level():
    with pytest.raises(ValidationError):
        AIProjectHealthSummary(summary='All good.', risk_level='catastrophic')


def test_summary_accepts_valid_risk_level():
    result = AIProjectHealthSummary(summary='All good.', risk_level='low')
    assert result.risk_level == 'low'

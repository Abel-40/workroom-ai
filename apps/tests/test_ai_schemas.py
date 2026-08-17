import uuid

import pytest
from pydantic import ValidationError

from apps.schemas.ai_schemas import AIProjectPlan, AIProjectPlanRequest, GeneratedTask


def test_project_plan_request_requires_a_title():
    with pytest.raises(ValidationError):
        AIProjectPlanRequest(generation_id=uuid.uuid4(), project_id=uuid.uuid4(), title='')


def test_generated_task_normalizes_priority_case():
    task = GeneratedTask(temporary_id='task-1', sequence=1, title='Do the thing', priority='HIGH')
    assert task.priority == 'high'


def test_generated_task_rejects_unknown_priority():
    with pytest.raises(ValidationError):
        GeneratedTask(temporary_id='task-1', sequence=1, title='Do the thing', priority='urgent')


def test_plan_defaults_to_empty_task_list():
    plan = AIProjectPlan(summary='A plan')
    assert plan.tasks == []

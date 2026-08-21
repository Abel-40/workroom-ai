import json
import uuid

import pytest

from apps.schemas.ai_schemas import (
    AIProjectPlanRegenerateRequest,
    AIProjectPlanRequest,
    DepartmentRef,
    GeneratedTask,
    RegenerateTaskRequest,
    TaskTypeRef,
)
from apps.services.ai_services import PlanValidationError, generate_project_plan, regenerate_project_plan_tasks
from apps.services.providers.base import AIProvider


class StubProvider(AIProvider):
    name = 'stub'

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


def make_request(departments=None, task_types=None):
    return AIProjectPlanRequest(
        generation_id=uuid.uuid4(), project_id=uuid.uuid4(), title='Build a support platform',
        description='A SaaS customer support platform.',
        departments=departments or [], task_types=task_types or [],
    )


@pytest.mark.asyncio
async def test_valid_plan_is_accepted():
    raw = json.dumps({
        'summary': 'A plan',
        'tasks': [
            {'temporary_id': 'task-1', 'sequence': 1, 'title': 'Define requirements'},
            {'temporary_id': 'task-2', 'sequence': 2, 'title': 'Design DB', 'dependency_ids': ['task-1']},
        ],
    })
    plan = await generate_project_plan(make_request(), provider=StubProvider(raw))
    assert len(plan.tasks) == 2
    assert plan.tasks[1].dependency_ids == ['task-1']


@pytest.mark.asyncio
async def test_unknown_dependency_id_is_rejected():
    raw = json.dumps({'tasks': [{'temporary_id': 'task-1', 'sequence': 1, 'title': 'X', 'dependency_ids': ['ghost']}]})
    with pytest.raises(PlanValidationError):
        await generate_project_plan(make_request(), provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_invented_department_id_is_rejected():
    real_department_id = uuid.uuid4()
    invented_id = str(uuid.uuid4())
    raw = json.dumps({'tasks': [{
        'temporary_id': 'task-1', 'sequence': 1, 'title': 'X', 'suggested_department_id': invented_id,
    }]})
    request = make_request(departments=[DepartmentRef(id=real_department_id, name='Engineering')])
    with pytest.raises(PlanValidationError):
        await generate_project_plan(request, provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_supplied_department_id_is_accepted():
    department_id = uuid.uuid4()
    raw = json.dumps({'tasks': [{
        'temporary_id': 'task-1', 'sequence': 1, 'title': 'X', 'suggested_department_id': str(department_id),
    }]})
    request = make_request(departments=[DepartmentRef(id=department_id, name='Engineering')])
    plan = await generate_project_plan(request, provider=StubProvider(raw))
    assert plan.tasks[0].suggested_department_id == department_id


@pytest.mark.asyncio
async def test_non_json_output_is_rejected():
    with pytest.raises(PlanValidationError):
        await generate_project_plan(make_request(), provider=StubProvider('Sure, here is your plan: ...'))


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_still_parsed():
    raw = '```json\n' + json.dumps({'tasks': [{'temporary_id': 't1', 'sequence': 1, 'title': 'X'}]}) + '\n```'
    plan = await generate_project_plan(make_request(), provider=StubProvider(raw))
    assert len(plan.tasks) == 1


def test_task_type_ref_roundtrip():
    ref = TaskTypeRef(id=uuid.uuid4(), name='Development')
    assert ref.name == 'Development'


def make_regenerate_request(existing_tasks=None, tasks_to_regenerate=None, departments=None, task_types=None):
    return AIProjectPlanRegenerateRequest(
        generation_id=uuid.uuid4(), project_id=uuid.uuid4(), title='Build a support platform',
        description='A SaaS customer support platform.',
        departments=departments or [], task_types=task_types or [],
        existing_tasks=existing_tasks or [],
        tasks_to_regenerate=tasks_to_regenerate or [
            RegenerateTaskRequest(temporary_id='task-2', title='Design DB', reviewer_comment='Add more detail.'),
        ],
    )


@pytest.mark.asyncio
async def test_regeneration_returns_only_the_requested_tasks():
    raw = json.dumps({'tasks': [{'temporary_id': 'task-2', 'title': 'Design DB schema', 'description': 'Detailed now.'}]})
    result = await regenerate_project_plan_tasks(make_regenerate_request(), provider=StubProvider(raw))
    assert len(result.tasks) == 1
    assert result.tasks[0].temporary_id == 'task-2'
    assert result.tasks[0].description == 'Detailed now.'


@pytest.mark.asyncio
async def test_regeneration_rejects_a_missing_requested_task():
    raw = json.dumps({'tasks': []})
    with pytest.raises(PlanValidationError):
        await regenerate_project_plan_tasks(make_regenerate_request(), provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_regeneration_rejects_an_extra_unrequested_task():
    raw = json.dumps({'tasks': [
        {'temporary_id': 'task-2', 'title': 'Design DB'},
        {'temporary_id': 'task-99', 'title': 'A task nobody asked to regenerate'},
    ]})
    with pytest.raises(PlanValidationError):
        await regenerate_project_plan_tasks(make_regenerate_request(), provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_regeneration_rejects_invented_department_id():
    real_department_id = uuid.uuid4()
    invented_id = str(uuid.uuid4())
    raw = json.dumps({'tasks': [{'temporary_id': 'task-2', 'title': 'Design DB', 'suggested_department_id': invented_id}]})
    request = make_regenerate_request(departments=[DepartmentRef(id=real_department_id, name='Engineering')])
    with pytest.raises(PlanValidationError):
        await regenerate_project_plan_tasks(request, provider=StubProvider(raw))


@pytest.mark.asyncio
async def test_regeneration_response_has_no_structural_fields_even_if_provider_sends_them():
    # A provider that ignores instructions and sends sequence/dependency_ids
    # anyway must not be able to smuggle a structural change through --
    # the response schema has no such fields, so they're simply dropped.
    raw = json.dumps({'tasks': [{
        'temporary_id': 'task-2', 'title': 'Design DB', 'sequence': 99, 'dependency_ids': ['task-1'],
    }]})
    result = await regenerate_project_plan_tasks(make_regenerate_request(), provider=StubProvider(raw))
    assert not hasattr(result.tasks[0], 'sequence')
    assert not hasattr(result.tasks[0], 'dependency_ids')


@pytest.mark.asyncio
async def test_regeneration_uses_existing_tasks_as_context_only():
    existing = [GeneratedTask(temporary_id='task-1', sequence=1, title='Define requirements')]
    raw = json.dumps({'tasks': [{'temporary_id': 'task-2', 'title': 'Design DB'}]})
    result = await regenerate_project_plan_tasks(
        make_regenerate_request(existing_tasks=existing), provider=StubProvider(raw),
    )
    assert len(result.tasks) == 1

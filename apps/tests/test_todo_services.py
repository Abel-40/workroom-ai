"""Structured-output validation for personal to-do generation.

The rules worth testing are the three Pydantic cannot express on its own:
a todo may only reference a task that was actually supplied, it may only land
inside the requested date window, and the cap must hold. All three are hard
rejections -- a plan that broke one is not repaired, it is refused.
"""

import json
import uuid
from datetime import date, timedelta

import pytest

from apps.schemas.todo_schemas import AITodoRequest
from apps.services.providers.base import AIProvider
from apps.services.todo_services import TodoValidationError, generate_task_todos

TASK_ID = uuid.uuid4()
TODAY = date(2026, 6, 1)


class StubProvider(AIProvider):
    name = 'stub'

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


def make_request(**overrides):
    body = dict(
        generation_id=uuid.uuid4(),
        today=TODAY,
        window_start=TODAY,
        window_end=TODAY + timedelta(days=2),
        max_todos=5,
        tasks=[{
            'task_id': TASK_ID,
            'title': 'Ship the landing page',
            'description': 'Rebuild the marketing landing page.',
            'status': 'In Progress',
            'priority': 'high',
            'project_title': 'Website Revamp',
            'deadline': TODAY + timedelta(days=5),
        }],
    )
    body.update(overrides)
    return AITodoRequest(**body)


def raw_plan(*todos):
    return json.dumps({'todos': list(todos)})


def todo(**overrides):
    body = {
        'task_id': str(TASK_ID), 'sequence': 1, 'title': 'Draft the hero copy',
        'notes': '', 'due_date': TODAY.isoformat(), 'estimated_minutes': 45,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_a_well_formed_plan_is_accepted():
    plan = await generate_task_todos(make_request(), provider=StubProvider(raw_plan(todo())))
    assert len(plan.todos) == 1
    assert plan.todos[0].title == 'Draft the hero copy'
    assert plan.todos[0].task_id == TASK_ID


@pytest.mark.asyncio
async def test_a_todo_referencing_an_unsupplied_task_is_rejected():
    """The model must never invent a task id -- Django would otherwise be
    asked to write a todo against work it never confirmed the requester owns."""
    rogue = raw_plan(todo(task_id=str(uuid.uuid4())))
    with pytest.raises(TodoValidationError, match='not supplied'):
        await generate_task_todos(make_request(), provider=StubProvider(rogue))


@pytest.mark.asyncio
async def test_a_due_date_after_the_window_is_rejected():
    late = raw_plan(todo(due_date=(TODAY + timedelta(days=9)).isoformat()))
    with pytest.raises(TodoValidationError, match='outside the requested window'):
        await generate_task_todos(make_request(), provider=StubProvider(late))


@pytest.mark.asyncio
async def test_a_due_date_before_the_window_is_rejected():
    early = raw_plan(todo(due_date=(TODAY - timedelta(days=1)).isoformat()))
    with pytest.raises(TodoValidationError, match='outside the requested window'):
        await generate_task_todos(make_request(), provider=StubProvider(early))


@pytest.mark.asyncio
async def test_the_window_boundaries_themselves_are_allowed():
    edge = raw_plan(
        todo(sequence=1, due_date=TODAY.isoformat()),
        todo(sequence=2, due_date=(TODAY + timedelta(days=2)).isoformat()),
    )
    plan = await generate_task_todos(make_request(), provider=StubProvider(edge))
    assert len(plan.todos) == 2


@pytest.mark.asyncio
async def test_exceeding_the_cap_is_rejected_rather_than_truncated():
    """Truncating would silently keep whichever items happened to come first,
    which is not the same as the model having chosen the important ones."""
    too_many = raw_plan(*[todo(sequence=i + 1, title=f'Step {i}') for i in range(6)])
    with pytest.raises(TodoValidationError, match='exceeding the requested cap'):
        await generate_task_todos(make_request(max_todos=5), provider=StubProvider(too_many))


@pytest.mark.asyncio
async def test_an_empty_plan_is_rejected():
    with pytest.raises(TodoValidationError, match='no todos'):
        await generate_task_todos(make_request(), provider=StubProvider(raw_plan()))


@pytest.mark.asyncio
async def test_non_json_output_is_rejected():
    with pytest.raises(TodoValidationError, match='valid JSON'):
        await generate_task_todos(make_request(), provider=StubProvider('Sure! Here are some todos:'))


@pytest.mark.asyncio
async def test_json_wrapped_in_code_fences_is_still_accepted():
    fenced = f'```json\n{raw_plan(todo())}\n```'
    plan = await generate_task_todos(make_request(), provider=StubProvider(fenced))
    assert len(plan.todos) == 1


@pytest.mark.asyncio
async def test_a_missing_required_field_is_rejected():
    broken = json.dumps({'todos': [{'task_id': str(TASK_ID), 'title': 'No date given', 'sequence': 1}]})
    with pytest.raises(TodoValidationError, match='schema validation'):
        await generate_task_todos(make_request(), provider=StubProvider(broken))


@pytest.mark.asyncio
async def test_titles_and_notes_are_stripped():
    padded = raw_plan(todo(title='   Draft the hero copy   ', notes='  Keep it short.  '))
    plan = await generate_task_todos(make_request(), provider=StubProvider(padded))
    assert plan.todos[0].title == 'Draft the hero copy'
    assert plan.todos[0].notes == 'Keep it short.'


def test_the_request_refuses_an_empty_task_list():
    """There is nothing to decompose without at least one assigned task, and
    an empty list would let a caller invoke the model for free."""
    with pytest.raises(ValueError):
        make_request(tasks=[])


def test_the_prompt_never_carries_a_person():
    """A todo is one individual's private list -- no assignee, department, or
    teammate name should ever reach the provider."""
    from apps.services.todo_services import _build_user_prompt

    prompt = _build_user_prompt(make_request())
    payload = json.loads(prompt)
    assert 'assignee' not in prompt.lower()
    assert set(payload['tasks'][0]) == {
        'task_id', 'title', 'description', 'status', 'priority', 'project_title', 'deadline',
    }

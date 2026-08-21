"""Project-plan generation: prompt construction, provider invocation, and
structured-output validation (AI_SERVICE_SPEC.md #3-4).

This never touches Django's database -- it returns a validated
AIProjectPlan and nothing else. Django independently re-validates suggested
department/task-type ids before persisting anything (Rule 9).
"""

import json
import logging

from pydantic import ValidationError

from apps.schemas.ai_schemas import (
    AIProjectPlan,
    AIProjectPlanRegenerateRequest,
    AIProjectPlanRegenerateResponse,
    AIProjectPlanRequest,
)
from apps.services.providers import AIProvider, get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Workroom's project planning assistant.

You generate a structured execution plan for a project. Rules:
- Output MUST be a single JSON object matching the supplied response_schema exactly. No prose, no markdown fences, no commentary outside the JSON.
- Break the project into actionable, concrete tasks ordered by logical sequence (field `sequence`, starting at 1).
- `dependency_ids` may only reference `temporary_id` values you generated in this same plan. Never invent ids.
- `suggested_department_id` and `suggested_task_type_id`, when set, MUST be chosen only from the department/task-type ids supplied to you. Never invent a department, task type, user, or assignee that wasn't supplied.
- Do not perform any action; you are only producing a plan for a human to review.
- Keep `estimated_effort` short if you provide it (e.g. "2h", "1d")."""


class PlanValidationError(Exception):
    """The provider returned something that doesn't match the contract."""


def _build_user_prompt(request: AIProjectPlanRequest) -> str:
    payload = {
        'project_title': request.title,
        'project_description': request.description,
        'project_requirements': request.requirements,
        'available_departments': [{'id': str(d.id), 'name': d.name} for d in request.departments],
        'available_task_types': [{'id': str(t.id), 'name': t.name} for t in request.task_types],
        'response_schema': {
            'summary': 'string',
            'tasks': [{
                'temporary_id': 'string, unique within this plan (e.g. "task-1")',
                'sequence': 'integer, starting at 1',
                'title': 'string',
                'description': 'string',
                'priority': 'one of: low, medium, high',
                'estimated_effort': 'short string, optional',
                'dependency_ids': 'list of temporary_id strings this task depends on',
                'suggested_department_id': 'one of available_departments[].id, or null',
                'suggested_task_type_id': 'one of available_task_types[].id, or null',
            }],
        },
    }
    return json.dumps(payload, indent=2)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = stripped.strip('`')
        if stripped.lower().startswith('json'):
            stripped = stripped[4:]
    return stripped.strip()


def parse_and_validate(raw_text: str, request: AIProjectPlanRequest) -> AIProjectPlan:
    try:
        data = json.loads(_strip_code_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f'Provider did not return valid JSON: {exc}') from exc

    try:
        plan = AIProjectPlan.model_validate(data)
    except ValidationError as exc:
        raise PlanValidationError(f'Provider output failed schema validation: {exc}') from exc

    known_ids = {task.temporary_id for task in plan.tasks}
    known_department_ids = {d.id for d in request.departments}
    known_task_type_ids = {t.id for t in request.task_types}

    for task in plan.tasks:
        unknown_deps = [dep for dep in task.dependency_ids if dep not in known_ids]
        if unknown_deps:
            raise PlanValidationError(f"Task '{task.temporary_id}' references unknown dependency ids: {unknown_deps}")
        if task.suggested_department_id and task.suggested_department_id not in known_department_ids:
            raise PlanValidationError(f"Task '{task.temporary_id}' suggested a department id that wasn't supplied.")
        if task.suggested_task_type_id and task.suggested_task_type_id not in known_task_type_ids:
            raise PlanValidationError(f"Task '{task.temporary_id}' suggested a task type id that wasn't supplied.")

    return plan


async def generate_project_plan(request: AIProjectPlanRequest, provider: AIProvider | None = None) -> AIProjectPlan:
    provider = provider or get_provider()
    user_prompt = _build_user_prompt(request)
    raw_text = await provider.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
    return parse_and_validate(raw_text, request)


REGENERATE_SYSTEM_PROMPT = """You are Workroom's project planning assistant, revising specific tasks in an \
already-reviewed plan based on human feedback.

Rules:
- Output MUST be a single JSON object matching the supplied response_schema exactly. No prose, no markdown fences, no commentary outside the JSON.
- `tasks` in your response MUST contain exactly one entry for each temporary_id listed in `tasks_to_revise`, and no other tasks. Do not touch, add, or drop any task outside that list.
- Use `existing_plan_context` (the rest of the plan) to keep your revision consistent in scope, naming, and technical level -- but do not rewrite or reference-change those tasks.
- Each entry in `tasks_to_revise` carries `reviewer_feedback`: treat it as the primary instruction for what to change about that task.
- `suggested_department_id`/`suggested_task_type_id`, when set, MUST be chosen only from the supplied department/task-type ids. Never invent a department, task type, user, or assignee.
- Do not perform any action; you are only producing revised task content for a human to review."""


def _build_regenerate_user_prompt(request: AIProjectPlanRegenerateRequest) -> str:
    payload = {
        'project_title': request.title,
        'project_description': request.description,
        'available_departments': [{'id': str(d.id), 'name': d.name} for d in request.departments],
        'available_task_types': [{'id': str(t.id), 'name': t.name} for t in request.task_types],
        'existing_plan_context': [task.model_dump(mode='json') for task in request.existing_tasks],
        'tasks_to_revise': [
            {
                'temporary_id': item.temporary_id,
                'current_title': item.title,
                'current_description': item.description,
                'reviewer_feedback': item.reviewer_comment,
            }
            for item in request.tasks_to_regenerate
        ],
        'response_schema': {
            'tasks': [{
                'temporary_id': 'string, must match one of tasks_to_revise[].temporary_id exactly',
                'title': 'string',
                'description': 'string',
                'priority': 'one of: low, medium, high',
                'estimated_effort': 'short string, optional',
                'suggested_department_id': 'one of available_departments[].id, or null',
                'suggested_task_type_id': 'one of available_task_types[].id, or null',
            }],
        },
    }
    return json.dumps(payload, indent=2)


def parse_and_validate_regeneration(
    raw_text: str, request: AIProjectPlanRegenerateRequest,
) -> AIProjectPlanRegenerateResponse:
    try:
        data = json.loads(_strip_code_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f'Provider did not return valid JSON: {exc}') from exc

    try:
        result = AIProjectPlanRegenerateResponse.model_validate(data)
    except ValidationError as exc:
        raise PlanValidationError(f'Provider output failed schema validation: {exc}') from exc

    requested_ids = {item.temporary_id for item in request.tasks_to_regenerate}
    returned_ids = {task.temporary_id for task in result.tasks}
    if returned_ids != requested_ids:
        raise PlanValidationError(
            f'Provider returned a different set of tasks than requested. Expected {requested_ids}, got {returned_ids}.'
        )

    known_department_ids = {d.id for d in request.departments}
    known_task_type_ids = {t.id for t in request.task_types}
    for task in result.tasks:
        if task.suggested_department_id and task.suggested_department_id not in known_department_ids:
            raise PlanValidationError(f"Task '{task.temporary_id}' suggested a department id that wasn't supplied.")
        if task.suggested_task_type_id and task.suggested_task_type_id not in known_task_type_ids:
            raise PlanValidationError(f"Task '{task.temporary_id}' suggested a task type id that wasn't supplied.")

    return result


async def regenerate_project_plan_tasks(
    request: AIProjectPlanRegenerateRequest, provider: AIProvider | None = None,
) -> AIProjectPlanRegenerateResponse:
    provider = provider or get_provider()
    user_prompt = _build_regenerate_user_prompt(request)
    raw_text = await provider.complete_json(system_prompt=REGENERATE_SYSTEM_PROMPT, user_prompt=user_prompt)
    return parse_and_validate_regeneration(raw_text, request)

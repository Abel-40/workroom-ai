"""Personal to-do generation: prompt construction, provider invocation, and
structured-output validation. Same shape as health_services.py -- forced-JSON
mode through the shared provider abstraction, no database access of any kind.

The validation here is the first of two passes. Django runs the second
(ai_agent/tasks_todos.py) against real Task rows and the requester's own
assignment set, because this service has no way to know whether the ids it
was handed are still assigned to the person who asked.
"""

import json
import logging
from datetime import timedelta

from pydantic import ValidationError

from apps.schemas.todo_schemas import AITodoPlan, AITodoRequest
from apps.services.providers import AIProvider, get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Workroom's personal to-do generator.

You are given a set of tasks that ONE person is already assigned to, that person's current date, and a date window. Break those tasks into concrete, individually completable steps for that one person's private checklist.

Output MUST be a single JSON object: {"todos": [{"task_id": string, "sequence": int, "title": string, "notes": string, "due_date": "YYYY-MM-DD", "estimated_minutes": int|null}]}. No prose outside the JSON.

Rules:
- Every task_id MUST be copied exactly from the input tasks. Never invent one.
- Every due_date MUST fall inside window_start..window_end inclusive. Prefer earlier days for steps belonging to tasks whose deadline is sooner.
- sequence starts at 1 and increases across the whole list, reflecting a sensible order of work.
- title is an action the person can actually finish in one sitting -- start with a verb, be specific to the task's own subject matter. Never restate the task title verbatim.
- notes is optional context, at most two sentences. Leave it as "" when the title says enough.
- estimated_minutes is your best guess of focused working time, or null when you genuinely cannot tell.
- Produce AT MOST max_todos items in total. Fewer is better than padding.
- Never mention, assign, or refer to any other person. This is one individual's private list.
- Never invent work outside what the given tasks describe."""


class TodoValidationError(Exception):
    """The provider returned something that doesn't match the contract."""


def _build_user_prompt(request: AITodoRequest) -> str:
    payload = {
        'today': request.today.isoformat(),
        'window_start': request.window_start.isoformat(),
        'window_end': request.window_end.isoformat(),
        'max_todos': request.max_todos,
        'instructions': request.instructions,
        'tasks': [
            {
                'task_id': str(task.task_id),
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'project_title': task.project_title,
                'deadline': task.deadline.isoformat() if task.deadline else None,
            }
            for task in request.tasks
        ],
    }
    return json.dumps(payload, indent=2)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = stripped.strip('`')
        if stripped.lower().startswith('json'):
            stripped = stripped[4:]
    return stripped.strip()


def parse_and_validate(raw_text: str, request: AITodoRequest) -> AITodoPlan:
    """Schema validation plus the three contract rules Pydantic alone cannot
    express: ids must come from the request, dates must land in the window,
    and the cap must hold. Each is a hard rejection rather than a silent
    repair -- a model that ignored the window probably ignored more than
    that, and Django would rather regenerate than persist a guess."""
    try:
        data = json.loads(_strip_code_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise TodoValidationError(f'Provider did not return valid JSON: {exc}') from exc

    try:
        plan = AITodoPlan.model_validate(data)
    except ValidationError as exc:
        raise TodoValidationError(f'Provider output failed schema validation: {exc}') from exc

    if not plan.todos:
        raise TodoValidationError('Provider returned no todos.')
    if len(plan.todos) > request.max_todos:
        raise TodoValidationError(
            f'Provider returned {len(plan.todos)} todos, exceeding the requested cap of {request.max_todos}.'
        )

    allowed_ids = {task.task_id for task in request.tasks}
    for todo in plan.todos:
        if todo.task_id not in allowed_ids:
            raise TodoValidationError(f'Provider referenced a task id that was not supplied: {todo.task_id}')
        if not request.window_start <= todo.due_date <= request.window_end:
            raise TodoValidationError(
                f"Todo '{todo.title}' has due_date {todo.due_date}, outside the requested window "
                f'{request.window_start}..{request.window_end}.'
            )
    return plan


async def generate_task_todos(request: AITodoRequest, provider: AIProvider | None = None) -> AITodoPlan:
    provider = provider or get_provider()
    raw_text = await provider.complete_json(
        system_prompt=SYSTEM_PROMPT, user_prompt=_build_user_prompt(request),
    )
    plan = parse_and_validate(raw_text, request)
    logger.info(
        'ai_todos.validated',
        extra={'generation_id': str(request.generation_id), 'todo_count': len(plan.todos)},
    )
    return plan


def default_window(today, days: int = 1):
    """The window used when a caller asks for "today" (days=1) or a short
    horizon. Exposed here so the Django side and this service agree on what
    a day-count means rather than each doing its own arithmetic."""
    return today, today + timedelta(days=max(days, 1) - 1)

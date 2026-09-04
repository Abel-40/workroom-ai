"""Contract for the personal to-do generation endpoint (/api/v1/task-todos).

Deliberately narrow. This endpoint turns work a specific person is *already
assigned to* into that person's own private checklist. It is not a planner:
it never proposes new work, never names other people, and never touches the
Workroom domain model -- Django resolves and re-validates everything before
a single row is written (DEVELOPMENT_RULES Rule 9).

Note what is absent from GeneratedTodo compared with ai_schemas.GeneratedTask:
no assignee, no department, no task type, no dependency graph. A todo belongs
to exactly one person -- the requester -- and there is nothing for the model
to route.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TodoSourceTask(BaseModel):
    """One task the requester is assigned to. Django only ever puts tasks it
    has confirmed are assigned to this requester into this list."""

    task_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    status: str = ''
    priority: str = ''
    project_title: str = ''
    # Naive date, already converted into the requester's timezone by Django.
    # The model must never do timezone arithmetic of its own.
    deadline: date | None = None


class AITodoRequest(BaseModel):
    generation_id: UUID
    # The requester's own "today", computed in their timezone by Django
    # (todos.services.user_today) -- the model has no clock and must not
    # assume one.
    today: date
    # The window the todos must land in. Django clamps anything outside it
    # rather than trusting these back (see ai_agent/tasks_todos.py).
    window_start: date
    window_end: date
    tasks: list[TodoSourceTask] = Field(min_length=1, max_length=25)
    # Free-text steer from the requester ("focus on the API work"), optional.
    instructions: str = Field(default='', max_length=2000)
    max_todos: int = Field(default=10, ge=1, le=30)


class GeneratedTodo(BaseModel):
    # Which source task this step belongs to. Django rejects the whole
    # generation if this is not one of the ids it sent.
    task_id: UUID
    sequence: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    notes: str = Field(default='', max_length=2000)
    due_date: date
    estimated_minutes: int | None = Field(default=None, ge=1, le=8 * 60)

    @field_validator('title', 'notes', mode='before')
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class AITodoPlan(BaseModel):
    todos: list[GeneratedTodo] = Field(default_factory=list)

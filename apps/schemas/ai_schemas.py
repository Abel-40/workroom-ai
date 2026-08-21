"""Contract for the AI project-decomposition endpoint (AI_SERVICE_SPEC.md #2).

Both sides of the Django <-> FastAPI boundary validate against this shape;
Django re-validates independently before persisting anything
(DEVELOPMENT_RULES Rule 9) rather than trusting this service's output.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Priority = Literal['low', 'medium', 'high']


class DepartmentRef(BaseModel):
    id: UUID
    name: str


class TaskTypeRef(BaseModel):
    id: UUID
    name: str


class AIProjectPlanRequest(BaseModel):
    generation_id: UUID
    project_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    requirements: str = ''
    departments: list[DepartmentRef] = Field(default_factory=list)
    task_types: list[TaskTypeRef] = Field(default_factory=list)


class GeneratedTask(BaseModel):
    temporary_id: str = Field(min_length=1, max_length=50)
    sequence: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    priority: Priority = 'medium'
    estimated_effort: str = ''
    dependency_ids: list[str] = Field(default_factory=list)
    suggested_department_id: UUID | None = None
    suggested_task_type_id: UUID | None = None

    @field_validator('priority', mode='before')
    @classmethod
    def _normalize_priority(cls, value):
        return value.lower() if isinstance(value, str) else value


class AIProjectPlan(BaseModel):
    summary: str = ''
    tasks: list[GeneratedTask] = Field(default_factory=list)


class RegenerateTaskRequest(BaseModel):
    """One task a human reviewer asked to be revised, plus the feedback that
    should drive the revision."""

    temporary_id: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    reviewer_comment: str = Field(min_length=1, max_length=2000)


class AIProjectPlanRegenerateRequest(BaseModel):
    """Revise a subset of an already-generated plan. Used both for
    comment-driven partial plan regeneration (``existing_tasks`` populated
    with the rest of the plan for context) and for regenerating a single
    already-saved task's content (``existing_tasks`` empty)."""

    generation_id: UUID
    project_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    departments: list[DepartmentRef] = Field(default_factory=list)
    task_types: list[TaskTypeRef] = Field(default_factory=list)
    existing_tasks: list[GeneratedTask] = Field(default_factory=list)
    tasks_to_regenerate: list[RegenerateTaskRequest] = Field(min_length=1)


class RegeneratedTask(BaseModel):
    """Content-only revision of one task -- deliberately has no `sequence`
    or `dependency_ids` field: a regeneration must never be able to reshuffle
    the plan's structure, only rewrite one task's own content."""

    temporary_id: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    priority: Priority = 'medium'
    estimated_effort: str = ''
    suggested_department_id: UUID | None = None
    suggested_task_type_id: UUID | None = None

    @field_validator('priority', mode='before')
    @classmethod
    def _normalize_priority(cls, value):
        return value.lower() if isinstance(value, str) else value


class AIProjectPlanRegenerateResponse(BaseModel):
    tasks: list[RegeneratedTask] = Field(default_factory=list)

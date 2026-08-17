"""Schemas for the project health summary endpoint (/api/v1/project-health-summary).

Kept separate from ai_schemas.py, which is scoped to the project-plan
decomposition contract only.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectStatsRef(BaseModel):
    """Mirrors analytics/services.py::get_project_stats' return shape
    exactly -- only real, currently-computable numbers. No blocked/dependency
    stat exists because task dependencies are never persisted on Task."""

    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    todo_tasks: int
    in_review_tasks: int
    overdue_tasks: int
    unassigned_tasks: int
    completion_percent: float


class AIProjectHealthRequest(BaseModel):
    summary_id: UUID
    project_id: UUID
    project_title: str
    project_description: str = ''
    stats: ProjectStatsRef


class AIProjectHealthSummary(BaseModel):
    summary: str = Field(max_length=2000)
    risk_level: Literal['low', 'medium', 'high']

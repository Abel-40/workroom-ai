"""Schemas for the scoped project assistant endpoint (/api/v1/assistant).

Kept separate from ai_schemas.py, which is scoped to the project-plan
decomposition contract only.
"""

from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class AIAssistantRequest(BaseModel):
    query_id: UUID
    project_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    project_title: str
    project_description: str = ''
    # Capped server-side by Django before this ever arrives (first 30).
    task_titles: list[str] = Field(default_factory=list)
    reference_url: HttpUrl | None = None
    # Already fetched (SSRF-safe) by Django -- this service does no network
    # I/O of its own besides the LLM call itself.
    reference_url_content: str = ''
    document_excerpts: list[str] = Field(default_factory=list)
    # Workroom pages the requester explicitly selected as context -- distinct
    # from document_excerpts, which are always included regardless of
    # selection (see Django's ai_agent/tasks_assistant.py).
    page_excerpts: list[str] = Field(default_factory=list)


class AIAssistantAnswer(BaseModel):
    """No `refused` field: this service returns raw text only. Django (the
    Celery task) parses the OUT_OF_SCOPE: sentinel when persisting, so that
    logic lives in exactly one place."""

    answer: str

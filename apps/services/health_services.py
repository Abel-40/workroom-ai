"""Project health summary: prompt construction, provider invocation, and
structured-output validation. Mirrors ai_services.py's structure -- this
output IS forced-JSON-mode (summary + risk_level enum), the exact shape
complete_json was built for, so it reuses the same Gemini/DeepSeek provider
abstraction as project-plan generation (no Groq here).

Never touches Django's database -- returns a validated AIProjectHealthSummary
and nothing else.
"""

import json
import logging

from pydantic import ValidationError

from apps.schemas.health_schemas import AIProjectHealthRequest, AIProjectHealthSummary
from apps.services.providers import AIProvider, get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Workroom's project health summarizer.

You are given ONLY these real, currently-computed statistics for a project: total_tasks, completed_tasks, in_progress_tasks, todo_tasks, in_review_tasks, overdue_tasks, unassigned_tasks, completion_percent.

Output MUST be a single JSON object: {"summary": string, "risk_level": "low"|"medium"|"high"}. No prose outside the JSON.

Write a short (2-4 sentence), natural-language summary of the project's current state using ONLY the numbers given. Call out overdue tasks and unassigned tasks by name if they are non-zero, and comment on completion progress.

Do NOT claim to detect blocked tasks, task dependencies, or any risk category not derivable from the exact numbers supplied -- that information does not exist and must never be implied.

Choose risk_level holistically from the numbers (e.g. high overdue count or many unassigned tasks relative to total suggests higher risk); do not invent a fixed threshold rule, use judgment."""


class HealthValidationError(Exception):
    """The provider returned something that doesn't match the contract."""


def _build_user_prompt(request: AIProjectHealthRequest) -> str:
    payload = {
        'project_title': request.project_title,
        'project_description': request.project_description,
        'stats': request.stats.model_dump(),
    }
    return json.dumps(payload, indent=2)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = stripped.strip('`')
        if stripped.lower().startswith('json'):
            stripped = stripped[4:]
    return stripped.strip()


def parse_and_validate(raw_text: str) -> AIProjectHealthSummary:
    try:
        data = json.loads(_strip_code_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise HealthValidationError(f'Provider did not return valid JSON: {exc}') from exc

    try:
        return AIProjectHealthSummary.model_validate(data)
    except ValidationError as exc:
        raise HealthValidationError(f'Provider output failed schema validation: {exc}') from exc


async def generate_health_summary(
    request: AIProjectHealthRequest, provider: AIProvider | None = None,
) -> AIProjectHealthSummary:
    provider = provider or get_provider()
    user_prompt = _build_user_prompt(request)
    raw_text = await provider.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
    return parse_and_validate(raw_text)

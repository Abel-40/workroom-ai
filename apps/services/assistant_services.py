"""Project assistant: prompt construction and provider invocation.

Never touches Django's database -- receives already-assembled context
(project title/description, task titles, a pre-fetched reference URL's
text, document excerpts) and returns raw answer text. Django's Celery task
(ai_agent/tasks_assistant.py) does the URL fetch, document reads, and the
OUT_OF_SCOPE: sentinel parsing; this module only talks to the LLM.
"""

import logging

from apps.schemas.assistant_schemas import AIAssistantRequest
from apps.services.providers.groq import GroqAssistantProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Workroom's project assistant, scoped strictly to the current project, its tasks, and the Workroom application itself.

You may help with: explaining/creating project structure, guidance on tasks within THIS project, and research (using web search or supplied reference content) that is directly relevant to THIS project or task.

You must refuse anything not about the current project, its tasks, or Workroom's own pages/settings -- including general knowledge questions, other companies' data, or anything unrelated to the context you were given.

If the question is out of scope, your ENTIRE response must be exactly: "OUT_OF_SCOPE: " followed by one short sentence explaining why. Do not answer the question in that case.

You have access to live web search for research questions that ARE in scope. You may also be given reference text from a URL the user supplied, and excerpts from the project's own text documents -- use them when relevant.

Never invent project data, task data, or Workroom features that were not supplied to you."""


class AssistantAnswerError(Exception):
    """The provider returned nothing usable (empty/whitespace-only)."""


def _build_user_prompt(request: AIAssistantRequest) -> str:
    lines = [
        f'Project title: {request.project_title}',
        f'Project description: {request.project_description or "(none provided)"}',
    ]
    if request.task_titles:
        lines.append('Existing tasks in this project:')
        lines.extend(f'- {title}' for title in request.task_titles)
    if request.reference_url_content:
        lines.append(f'Reference content from the URL the user supplied ({request.reference_url}):')
        lines.append(request.reference_url_content)
    if request.document_excerpts:
        lines.append("Excerpts from this project's own documents:")
        for index, excerpt in enumerate(request.document_excerpts, start=1):
            lines.append(f'--- Document {index} ---')
            lines.append(excerpt)
    if request.page_excerpts:
        lines.append('Excerpts from Workroom pages the user selected as context:')
        for index, excerpt in enumerate(request.page_excerpts, start=1):
            lines.append(f'--- Page {index} ---')
            lines.append(excerpt)
    lines.append(f'Question: {request.question}')
    return '\n'.join(lines)


async def generate_assistant_answer(request: AIAssistantRequest, provider: GroqAssistantProvider | None = None) -> str:
    provider = provider or GroqAssistantProvider()
    user_prompt = _build_user_prompt(request)
    answer = await provider.complete_text(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
    if not answer or not answer.strip():
        raise AssistantAnswerError('Provider returned an empty answer.')
    return answer.strip()

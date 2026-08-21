import logging
import time

from fastapi import Depends, FastAPI, Header, HTTPException

from apps.core.config import settings
from apps.schemas.ai_schemas import AIProjectPlanRegenerateRequest, AIProjectPlanRequest
from apps.schemas.assistant_schemas import AIAssistantRequest
from apps.schemas.health_schemas import AIProjectHealthRequest
from apps.services.ai_services import (
    PlanValidationError,
    generate_project_plan,
    regenerate_project_plan_tasks,
)
from apps.services.assistant_services import AssistantAnswerError, generate_assistant_answer
from apps.services.health_services import HealthValidationError, generate_health_summary
from apps.services.providers import PermanentProviderError, TransientProviderError, get_provider
from apps.services.providers.groq import get_groq_assistant_provider
from apps.utils.response import error_response, success_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title='Workroom AI Service', version='1.0.0')


@app.get('/check')
async def check():
    """Health endpoint (AI_SERVICE_SPEC.md #6)."""
    return {'server_status': 'running'}


def verify_service_token(x_service_token: str | None = Header(default=None)):
    """Django's Celery worker is the only intended caller. An empty
    SERVICE_AUTH_TOKEN disables the check for local dev; it must be set in
    any real deployment so this service can't be invoked (and burn LLM
    credits) by anything else that can reach it on the network."""
    if settings.SERVICE_AUTH_TOKEN and x_service_token != settings.SERVICE_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid or missing service token.')


@app.post('/api/v1/project-plan', dependencies=[Depends(verify_service_token)])
async def create_project_plan(request: AIProjectPlanRequest):
    started = time.monotonic()
    log_context = {'generation_id': str(request.generation_id), 'project_id': str(request.project_id)}

    try:
        provider = get_provider()
    except PermanentProviderError as exc:
        logger.error('ai_plan.provider_unavailable', extra=log_context)
        return error_response(502, 'AI provider is not configured.', error={'type': 'permanent', 'detail': str(exc)})

    try:
        plan = await generate_project_plan(request, provider=provider)
    except TransientProviderError as exc:
        logger.warning('ai_plan.transient_failure', extra=log_context)
        return error_response(
            503, 'AI provider temporarily unavailable.', error={'type': 'transient', 'detail': str(exc)},
        )
    except PermanentProviderError as exc:
        logger.error('ai_plan.permanent_failure', extra=log_context)
        return error_response(
            502, 'AI provider request failed.', error={'type': 'permanent', 'detail': str(exc)},
        )
    except PlanValidationError as exc:
        logger.error('ai_plan.invalid_output', extra=log_context)
        return error_response(
            422, 'AI provider output failed validation.', error={'type': 'invalid_output', 'detail': str(exc)},
        )

    duration = time.monotonic() - started
    logger.info('ai_plan.completed', extra={
        **log_context, 'duration_seconds': round(duration, 2), 'task_count': len(plan.tasks),
    })
    return success_response(200, 'Project plan generated successfully.', data={
        'provider': provider.name, 'model': getattr(provider, 'model', ''),
        **plan.model_dump(mode='json'),
    })


@app.post('/api/v1/project-plan-regenerate', dependencies=[Depends(verify_service_token)])
async def create_project_plan_regeneration(request: AIProjectPlanRegenerateRequest):
    started = time.monotonic()
    log_context = {'generation_id': str(request.generation_id), 'project_id': str(request.project_id)}

    try:
        provider = get_provider()
    except PermanentProviderError as exc:
        logger.error('ai_plan_regenerate.provider_unavailable', extra=log_context)
        return error_response(502, 'AI provider is not configured.', error={'type': 'permanent', 'detail': str(exc)})

    try:
        result = await regenerate_project_plan_tasks(request, provider=provider)
    except TransientProviderError as exc:
        logger.warning('ai_plan_regenerate.transient_failure', extra=log_context)
        return error_response(
            503, 'AI provider temporarily unavailable.', error={'type': 'transient', 'detail': str(exc)},
        )
    except PermanentProviderError as exc:
        logger.error('ai_plan_regenerate.permanent_failure', extra=log_context)
        return error_response(
            502, 'AI provider request failed.', error={'type': 'permanent', 'detail': str(exc)},
        )
    except PlanValidationError as exc:
        logger.error('ai_plan_regenerate.invalid_output', extra=log_context)
        return error_response(
            422, 'AI provider output failed validation.', error={'type': 'invalid_output', 'detail': str(exc)},
        )

    duration = time.monotonic() - started
    logger.info('ai_plan_regenerate.completed', extra={
        **log_context, 'duration_seconds': round(duration, 2), 'task_count': len(result.tasks),
    })
    return success_response(200, 'Plan tasks regenerated successfully.', data={
        'provider': provider.name, 'model': getattr(provider, 'model', ''),
        **result.model_dump(mode='json'),
    })


@app.post('/api/v1/assistant', dependencies=[Depends(verify_service_token)])
async def create_assistant_answer(request: AIAssistantRequest):
    started = time.monotonic()
    log_context = {'query_id': str(request.query_id), 'project_id': str(request.project_id)}

    try:
        provider = get_groq_assistant_provider()
    except PermanentProviderError as exc:
        logger.error('ai_assistant.provider_unavailable', extra=log_context)
        return error_response(502, 'AI provider is not configured.', error={'type': 'permanent', 'detail': str(exc)})

    try:
        answer = await generate_assistant_answer(request, provider=provider)
    except TransientProviderError as exc:
        logger.warning('ai_assistant.transient_failure', extra=log_context)
        return error_response(
            503, 'AI provider temporarily unavailable.', error={'type': 'transient', 'detail': str(exc)},
        )
    except PermanentProviderError as exc:
        logger.error('ai_assistant.permanent_failure', extra=log_context)
        return error_response(502, 'AI provider request failed.', error={'type': 'permanent', 'detail': str(exc)})
    except AssistantAnswerError as exc:
        logger.error('ai_assistant.invalid_output', extra=log_context)
        return error_response(
            422, 'AI provider output failed validation.', error={'type': 'invalid_output', 'detail': str(exc)},
        )

    duration = time.monotonic() - started
    logger.info('ai_assistant.completed', extra={**log_context, 'duration_seconds': round(duration, 2)})
    return success_response(200, 'Assistant answer generated successfully.', data={
        'provider': provider.name, 'model': getattr(provider, 'model', ''), 'answer': answer,
    })


@app.post('/api/v1/project-health-summary', dependencies=[Depends(verify_service_token)])
async def create_health_summary(request: AIProjectHealthRequest):
    started = time.monotonic()
    log_context = {'summary_id': str(request.summary_id), 'project_id': str(request.project_id)}

    try:
        provider = get_provider()
    except PermanentProviderError as exc:
        logger.error('ai_health_summary.provider_unavailable', extra=log_context)
        return error_response(502, 'AI provider is not configured.', error={'type': 'permanent', 'detail': str(exc)})

    try:
        result = await generate_health_summary(request, provider=provider)
    except TransientProviderError as exc:
        logger.warning('ai_health_summary.transient_failure', extra=log_context)
        return error_response(
            503, 'AI provider temporarily unavailable.', error={'type': 'transient', 'detail': str(exc)},
        )
    except PermanentProviderError as exc:
        logger.error('ai_health_summary.permanent_failure', extra=log_context)
        return error_response(502, 'AI provider request failed.', error={'type': 'permanent', 'detail': str(exc)})
    except HealthValidationError as exc:
        logger.error('ai_health_summary.invalid_output', extra=log_context)
        return error_response(
            422, 'AI provider output failed validation.', error={'type': 'invalid_output', 'detail': str(exc)},
        )

    duration = time.monotonic() - started
    logger.info('ai_health_summary.completed', extra={**log_context, 'duration_seconds': round(duration, 2)})
    return success_response(200, 'Project health summary generated successfully.', data={
        'provider': provider.name, 'model': getattr(provider, 'model', ''),
        **result.model_dump(mode='json'),
    })

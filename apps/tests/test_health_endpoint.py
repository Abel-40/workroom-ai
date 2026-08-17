from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.main import app
from apps.schemas.health_schemas import AIProjectHealthSummary
from apps.services.providers import TransientProviderError

client = TestClient(app)


def _valid_request_body():
    return {
        'summary_id': '11111111-1111-1111-1111-111111111111',
        'project_id': '22222222-2222-2222-2222-222222222222',
        'project_title': 'Support platform',
        'stats': {
            'total_tasks': 10, 'completed_tasks': 4, 'in_progress_tasks': 3, 'todo_tasks': 2,
            'in_review_tasks': 1, 'overdue_tasks': 2, 'unassigned_tasks': 3, 'completion_percent': 40.0,
        },
    }


def test_health_summary_endpoint_returns_summary():
    fake_result = AIProjectHealthSummary(summary='On track.', risk_level='low')
    with patch('apps.main.generate_health_summary', new=AsyncMock(return_value=fake_result)):
        response = client.post('/api/v1/project-health-summary', json=_valid_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']['risk_level'] == 'low'


def test_health_summary_endpoint_maps_transient_provider_error():
    with patch('apps.main.generate_health_summary', new=AsyncMock(side_effect=TransientProviderError('rate limited'))):
        response = client.post('/api/v1/project-health-summary', json=_valid_request_body())
    assert response.status_code == 503
    assert response.json()['success'] is False


def test_health_summary_endpoint_requires_service_token_when_configured():
    with patch('apps.main.settings.SERVICE_AUTH_TOKEN', 'secret'):
        response = client.post('/api/v1/project-health-summary', json=_valid_request_body())
    assert response.status_code == 401

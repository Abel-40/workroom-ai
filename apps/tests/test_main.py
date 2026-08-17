from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.main import app
from apps.schemas.ai_schemas import AIProjectPlan, GeneratedTask
from apps.services.providers import TransientProviderError

client = TestClient(app)


def _valid_request_body():
    return {
        'generation_id': '11111111-1111-1111-1111-111111111111',
        'project_id': '22222222-2222-2222-2222-222222222222',
        'title': 'Build a support platform',
    }


def test_health_check():
    response = client.get('/check')
    assert response.status_code == 200
    assert response.json() == {'server_status': 'running'}


def test_project_plan_endpoint_returns_generated_plan():
    fake_plan = AIProjectPlan(summary='ok', tasks=[GeneratedTask(temporary_id='t1', sequence=1, title='Do it')])
    with patch('apps.main.generate_project_plan', new=AsyncMock(return_value=fake_plan)):
        response = client.post('/api/v1/project-plan', json=_valid_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']['tasks'][0]['title'] == 'Do it'


def test_project_plan_endpoint_maps_transient_provider_error():
    with patch('apps.main.generate_project_plan', new=AsyncMock(side_effect=TransientProviderError('rate limited'))):
        response = client.post('/api/v1/project-plan', json=_valid_request_body())
    assert response.status_code == 503
    assert response.json()['success'] is False


def test_project_plan_endpoint_requires_service_token_when_configured():
    with patch('apps.main.settings.SERVICE_AUTH_TOKEN', 'secret'):
        response = client.post('/api/v1/project-plan', json=_valid_request_body())
    assert response.status_code == 401


def test_project_plan_endpoint_accepts_correct_service_token():
    fake_plan = AIProjectPlan(summary='ok', tasks=[])
    with patch('apps.main.settings.SERVICE_AUTH_TOKEN', 'secret'), \
         patch('apps.main.generate_project_plan', new=AsyncMock(return_value=fake_plan)):
        response = client.post(
            '/api/v1/project-plan', json=_valid_request_body(), headers={'X-Service-Token': 'secret'},
        )
    assert response.status_code == 200

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.main import app
from apps.services.providers import TransientProviderError

client = TestClient(app)


def _valid_request_body():
    return {
        'query_id': '11111111-1111-1111-1111-111111111111',
        'project_id': '22222222-2222-2222-2222-222222222222',
        'question': 'What tasks are still To Do?',
        'project_title': 'Support platform',
    }


def test_assistant_endpoint_returns_answer():
    with patch('apps.main.generate_assistant_answer', new=AsyncMock(return_value='You have 2 tasks left.')):
        response = client.post('/api/v1/assistant', json=_valid_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']['answer'] == 'You have 2 tasks left.'


def test_assistant_endpoint_maps_transient_provider_error():
    with patch('apps.main.generate_assistant_answer', new=AsyncMock(side_effect=TransientProviderError('rate limited'))):
        response = client.post('/api/v1/assistant', json=_valid_request_body())
    assert response.status_code == 503
    assert response.json()['success'] is False


def test_assistant_endpoint_requires_service_token_when_configured():
    with patch('apps.main.settings.SERVICE_AUTH_TOKEN', 'secret'):
        response = client.post('/api/v1/assistant', json=_valid_request_body())
    assert response.status_code == 401


def test_assistant_endpoint_accepts_correct_service_token():
    with patch('apps.main.settings.SERVICE_AUTH_TOKEN', 'secret'), \
         patch('apps.main.generate_assistant_answer', new=AsyncMock(return_value='ok')):
        response = client.post(
            '/api/v1/assistant', json=_valid_request_body(), headers={'X-Service-Token': 'secret'},
        )
    assert response.status_code == 200

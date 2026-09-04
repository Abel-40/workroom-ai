from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.main import app
from apps.schemas.todo_schemas import AITodoPlan, GeneratedTodo
from apps.services.providers import PermanentProviderError, TransientProviderError
from apps.services.todo_services import TodoValidationError

client = TestClient(app)


@contextmanager
def stub_provider():
    """The endpoint resolves a provider before it ever calls the generator, so
    a test that only patches the generator would really be asserting that a
    real API key happens to be configured in the environment. Stub both, so
    these stay hermetic."""
    # A plain namespace, not a Mock: the endpoint reads provider.name into
    # the JSON response, and Mock(name=...) sets the mock's repr rather
    # than a .name attribute, so a Mock lands an unserializable object there.
    with patch('apps.main.get_provider', return_value=SimpleNamespace(name='stub-provider', model='stub-model')):
        yield


TASK_ID = '33333333-3333-3333-3333-333333333333'


def _valid_request_body(**overrides):
    body = {
        'generation_id': '11111111-1111-1111-1111-111111111111',
        'today': '2026-06-01',
        'window_start': '2026-06-01',
        'window_end': '2026-06-03',
        'max_todos': 5,
        'tasks': [{
            'task_id': TASK_ID,
            'title': 'Ship the landing page',
            'description': 'Rebuild the marketing landing page.',
            'status': 'In Progress',
            'priority': 'high',
            'project_title': 'Website Revamp',
            'deadline': '2026-06-06',
        }],
    }
    body.update(overrides)
    return body


def _fake_plan():
    return AITodoPlan(todos=[GeneratedTodo(
        task_id=TASK_ID, sequence=1, title='Draft the hero copy', due_date='2026-06-01', estimated_minutes=45,
    )])


def test_endpoint_returns_the_generated_todos():
    with stub_provider(), patch('apps.main.generate_task_todos', new=AsyncMock(return_value=_fake_plan())):
        response = client.post('/api/v1/task-todos', json=_valid_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert len(body['data']['todos']) == 1
    assert body['data']['todos'][0]['title'] == 'Draft the hero copy'


@pytest.mark.parametrize(
    ('exception', 'expected_status'),
    [
        (TransientProviderError('rate limited'), 503),
        (PermanentProviderError('bad api key'), 502),
        (TodoValidationError('window violated'), 422),
    ],
)
def test_endpoint_maps_each_failure_to_its_own_status(exception, expected_status):
    """Django's Celery task retries on 5xx but fails the generation outright
    on 422, so these mappings are load-bearing, not cosmetic."""
    with stub_provider(), patch('apps.main.generate_task_todos', new=AsyncMock(side_effect=exception)):
        response = client.post('/api/v1/task-todos', json=_valid_request_body())
    assert response.status_code == expected_status
    assert response.json()['success'] is False


def test_endpoint_rejects_a_request_with_no_tasks():
    response = client.post('/api/v1/task-todos', json=_valid_request_body(tasks=[]))
    assert response.status_code == 422


def test_endpoint_rejects_a_task_list_beyond_the_contract_limit():
    tasks = [dict(_valid_request_body()['tasks'][0], title=f'Task {i}') for i in range(26)]
    response = client.post('/api/v1/task-todos', json=_valid_request_body(tasks=tasks))
    assert response.status_code == 422


def test_a_provider_error_never_leaks_the_raw_detail_as_the_user_message():
    """The detail stays in the structured error object for the worker's logs;
    the human-readable message must stay generic."""
    with stub_provider(), patch(
        'apps.main.generate_task_todos', new=AsyncMock(side_effect=PermanentProviderError('sk-live-secret')),
    ):
        response = client.post('/api/v1/task-todos', json=_valid_request_body())
    assert 'sk-live-secret' not in response.json()['message']

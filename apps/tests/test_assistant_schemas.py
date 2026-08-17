import uuid

import pytest
from pydantic import ValidationError

from apps.schemas.assistant_schemas import AIAssistantAnswer, AIAssistantRequest


def test_question_is_required():
    with pytest.raises(ValidationError):
        AIAssistantRequest(
            query_id=uuid.uuid4(), project_id=uuid.uuid4(), question='', project_title='X',
        )


def test_reference_url_rejects_non_http_scheme():
    with pytest.raises(ValidationError):
        AIAssistantRequest(
            query_id=uuid.uuid4(), project_id=uuid.uuid4(), question='Q', project_title='X',
            reference_url='ftp://example.com/file',
        )


def test_defaults_are_empty():
    request = AIAssistantRequest(query_id=uuid.uuid4(), project_id=uuid.uuid4(), question='Q', project_title='X')
    assert request.task_titles == []
    assert request.document_excerpts == []
    assert request.reference_url_content == ''


def test_answer_roundtrip():
    answer = AIAssistantAnswer(answer='Here you go.')
    assert answer.answer == 'Here you go.'
    assert not hasattr(answer, 'refused')

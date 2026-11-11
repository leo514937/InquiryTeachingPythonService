import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import UserWorkspaceRoleModel
from app.workspace.models import WorkspaceBase


@pytest.fixture
def setup_document(monkeypatch):
    from app.workspace.api import CreateWorkspace, LessonImport, add_workspace, add_lesson_document
    from app.workspace.integrations.llm import StrictLLM
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(UserWorkspaceRoleModel(user_id='teacher', role_category='teacher', created_at='now'))
        db.commit()
        user = SimpleNamespace(id='teacher', user_role='teacher')
        ws = add_workspace(CreateWorkspace(title='课'), db, user)['data']['id']
        doc = add_lesson_document(ws, LessonImport(title='课', text='教学目标\n理解分类'), db, user)['data']
        calls = []
        def complete(self, prompt, message):
            calls.append(json.loads(message))
            return json.dumps({'analysis': '目标可以更具体。', 'suggestion': '说明分类理由。'}, ensure_ascii=False)
        monkeypatch.setattr(StrictLLM, 'complete', complete)
        yield db, user, ws, doc, calls
    engine.dispose()


def test_general_assistant_uses_current_document_without_sources(setup_document):
    from app.workspace.api import LessonAssistantInput, lesson_assistant
    db, user, ws, doc, calls = setup_document
    payload = LessonAssistantInput(expected_version=1, instruction='分析教案', selected_text='')
    data = lesson_assistant(ws, doc['id'], payload, db, user)['data']
    assert data['evidence_status'] == 'no_sources'
    assert data['analysis'] == '目标可以更具体。'
    assert calls[0]['document'] == '教学目标\n理解分类'


def test_assistant_checks_selection_and_version_before_model_call(setup_document):
    from app.workspace.api import LessonAssistantInput, lesson_assistant
    db, user, ws, doc, calls = setup_document
    for data in [dict(expected_version=2, instruction='优化', selected_text=''),
                 dict(expected_version=1, instruction='优化', selected_text='不存在')]:
        with pytest.raises(HTTPException) as exc:
            lesson_assistant(ws, doc['id'], LessonAssistantInput(**data), db, user)
        assert exc.value.status_code == 409
    assert not calls


def test_selected_excerpt_is_sent_without_replacing_document(setup_document):
    from app.workspace.api import LessonAssistantInput, lesson_assistant, get_workspace
    db, user, ws, doc, calls = setup_document
    data = lesson_assistant(ws, doc['id'], LessonAssistantInput(expected_version=1, instruction='优化', selected_text='理解分类'), db, user)['data']
    assert calls[0]['selection'] == '理解分类'
    assert data['suggestion'] == '说明分类理由。'
    assert get_workspace(ws, db, user)['data']['artifacts'][0]['version'] == 1


def test_invalid_model_response_does_not_modify_document(setup_document, monkeypatch):
    from app.workspace.api import LessonAssistantInput, lesson_assistant, get_workspace
    from app.workspace.integrations.llm import StrictLLM
    db, user, ws, doc, _ = setup_document
    monkeypatch.setattr(StrictLLM, 'complete', lambda *args: '不是 JSON')
    with pytest.raises(HTTPException) as exc:
        lesson_assistant(ws, doc['id'], LessonAssistantInput(expected_version=1, instruction='分析'), db, user)
    assert exc.value.status_code == 502
    assert get_workspace(ws, db, user)['data']['artifacts'][0]['version'] == 1


def test_model_unavailable_does_not_fabricate_result(setup_document, monkeypatch):
    from app.workspace.api import LessonAssistantInput, lesson_assistant
    from app.workspace.integrations.llm import StrictLLM, ModelUnavailable
    db, user, ws, doc, _ = setup_document
    def fail(*args):
        raise ModelUnavailable('模型未配置')
    monkeypatch.setattr(StrictLLM, 'complete', fail)
    with pytest.raises(HTTPException) as exc:
        lesson_assistant(ws, doc['id'], LessonAssistantInput(expected_version=1, instruction='分析'), db, user)
    assert exc.value.status_code == 503


def test_analysis_rejects_version_changed_while_model_runs(setup_document, monkeypatch):
    from app.workspace.api import LessonAssistantInput, lesson_assistant
    from app.workspace.integrations.llm import StrictLLM
    from app.workspace.models import Artifact
    db, user, ws, doc, _ = setup_document
    def change(*args):
        row = db.get(Artifact, doc['id'])
        row.version = 2
        db.flush()
        return json.dumps({'analysis': '分析', 'suggestion': ''})
    monkeypatch.setattr(StrictLLM, 'complete', change)
    with pytest.raises(HTTPException) as exc:
        lesson_assistant(ws, doc['id'], LessonAssistantInput(expected_version=1, instruction='分析'), db, user)
    assert exc.value.status_code == 409

from types import SimpleNamespace

import pytest
import os
import subprocess
import sys
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import UserWorkspaceRoleModel
from app.workspace.api import CreateWorkspace, RecordInput, NarrativeInput, add_workspace, add_reflection, add_record, get_workspace, add_narrative, make_snapshot, snapshot_print, snapshot_docx
from app.workspace.models import WorkspaceBase


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([
            UserWorkspaceRoleModel(user_id='teacher', role_category='teacher', created_at='now'),
            UserWorkspaceRoleModel(user_id='other', role_category='teacher', created_at='now'),
        ])
        session.commit()
        yield session
    engine.dispose()


def test_workspace_ownership_and_persistent_reflection(db):
    teacher = SimpleNamespace(id='teacher', user_role='teacher')
    workspace_id = add_workspace(CreateWorkspace(title='光的反射'), db, teacher)['data']['id']
    experiment_id = add_reflection(workspace_id, db, teacher)['data']['id']
    recorded = add_record(workspace_id, experiment_id, RecordInput(angle=45, idempotency_key='a'), db, teacher)
    assert recorded['data']['content']['records'][0]['reflected_angle_deg'] == 45
    assert len(get_workspace(workspace_id, db, teacher)['data']['artifacts']) == 2
    other = SimpleNamespace(id='other', user_role='teacher')
    with pytest.raises(HTTPException) as missing:
        get_workspace(workspace_id, db, other)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as denied:
        add_workspace(CreateWorkspace(title='无权'), db, SimpleNamespace(id='parent', user_role='parent'))
    assert denied.value.status_code == 403


def test_report_snapshot_export_uses_same_content(db):
    from io import BytesIO
    from docx import Document

    teacher = SimpleNamespace(id='teacher', user_role='teacher')
    workspace_id = add_workspace(CreateWorkspace(title='反射'), db, teacher)['data']['id']
    add_narrative(workspace_id, NarrativeInput(section_key='teaching_context', title='学情', paragraphs=['学生已有经验']), db, teacher)
    snapshot_id = make_snapshot(workspace_id, db, teacher)['data']['id']
    printed = snapshot_print(workspace_id, snapshot_id, db, teacher)['data']
    exported = snapshot_docx(workspace_id, snapshot_id, db, teacher)
    assert printed['sections'][0]['paragraphs'] == ['学生已有经验']
    assert '学生已有经验' in [p.text for p in Document(BytesIO(exported.body)).paragraphs]


def test_approval_rejects_workspace_changed_after_review_started(db):
    from app.workspace.api import RunApproval, approve_run
    from app.workspace.runtime.runs import create_run
    teacher = SimpleNamespace(id='teacher', user_role='teacher')
    workspace_id = add_workspace(CreateWorkspace(title='反射'), db, teacher)['data']['id']
    run = create_run(db, workspace_id, teacher.id, '需求', 'experiment', 'key')
    run.status = 'waiting_review'
    db.commit()
    add_reflection(workspace_id, db, teacher)
    with pytest.raises(HTTPException) as conflict:
        approve_run(workspace_id, run.id, RunApproval(decision='approve'), db, teacher)
    assert conflict.value.status_code == 409


def test_approval_cannot_bypass_missing_teaching_information(db):
    from app.workspace.api import RunApproval, approve_run
    from app.workspace.runtime.runs import create_run
    teacher = SimpleNamespace(id='teacher', user_role='teacher')
    workspace_id = add_workspace(CreateWorkspace(title='反射'), db, teacher)['data']['id']
    run = create_run(db, workspace_id, teacher.id, '需求', 'experiment', 'missing')
    run.status = 'waiting_review'
    run.error = '实验描述、材料或安全措施不完整，请教师审核。'
    db.commit()
    with pytest.raises(HTTPException) as conflict:
        approve_run(workspace_id, run.id, RunApproval(decision='approve'), db, teacher)
    assert conflict.value.status_code == 409
    db.refresh(run)
    assert run.status == 'waiting_review'


def test_run_response_distinguishes_risk_approval_from_missing_information(db):
    from app.workspace.api import get_run
    from app.workspace.runtime.runs import create_run
    teacher = SimpleNamespace(id='teacher', user_role='teacher')
    workspace_id = add_workspace(CreateWorkspace(title='反射'), db, teacher)['data']['id']
    run = create_run(db, workspace_id, teacher.id, '需求', 'experiment', 'review')
    run.status = 'waiting_review'
    run.error = '实验描述、材料或安全措施不完整，请教师审核。'
    db.commit()
    assert get_run(workspace_id, run.id, db, teacher)['data']['review_approvable'] is False
    run.error = '实验可能涉及安全风险，请教师审核。'
    db.commit()
    assert get_run(workspace_id, run.id, db, teacher)['data']['review_approvable'] is True


def test_http_routes_enforce_workspace_ownership():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from app.core.auth import get_current_user
    from app.db.database import get_db
    from app.workspace.api import router

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    WorkspaceBase.metadata.create_all(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    with Session(engine) as session:
        session.add_all([UserWorkspaceRoleModel(user_id=user, role_category='teacher', created_at='now') for user in ('teacher', 'other')])
        session.commit()
    actor = SimpleNamespace(id='teacher', user_role='teacher')
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        result = client.post('/api/inquiry-workspaces', json={'title': '光的反射'})
        assert result.status_code == 200
        workspace_id = result.json()['data']['id']
        experiment = client.post(f'/api/inquiry-workspaces/{workspace_id}/experiments/reflection').json()['data']
        queued = client.post(f'/api/inquiry-workspaces/{workspace_id}/runs', json={'goal': '反射实验', 'mode': 'experiment', 'idempotency_key': 'run-key'})
        assert queued.status_code == 200 and queued.json()['data']['status'] == 'queued'
        run_id = queued.json()['data']['id']
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}').json()['data']['latest_run']['id'] == run_id
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}').json()['data']['status'] == 'queued'
        events = client.get(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}/events?after=0')
        assert events.status_code == 200 and 'event: queued' in events.text and 'id: 1' in events.text
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}/events?after=1').text == ''
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}/events', headers={'Last-Event-ID': '1'}).text == ''
        assert client.post(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}/cancel').json()['data']['status'] == 'cancelled'
        assert client.post(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}/resume', json={'decision': 'approve'}).status_code == 409
        updated = client.patch(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{experiment["id"]}', json={'expected_version': 1, 'content': {**experiment['content'], 'title': '修改实验'}})
        assert updated.status_code == 200 and updated.json()['data']['version'] == 2
        empty_replan = client.post(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{experiment["id"]}/replan', json={'expected_version': 2, 'instruction': '局部更新', 'idempotency_key': 'replan-key'})
        assert empty_replan.status_code == 409
        versions = client.get(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{experiment["id"]}/versions')
        assert [v['version'] for v in versions.json()['data']] == [1, 2]
        restored = client.post(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{experiment["id"]}/restore', json={'expected_version': 2, 'version': 1})
        assert restored.status_code == 200 and restored.json()['data']['version'] == 3
        result = client.post(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{experiment["id"]}/records', json={'angle': 30, 'idempotency_key': 'test'})
        assert result.status_code == 200
        assert result.json()['data']['content']['records'][0]['reflected_angle_deg'] == 30
        record = result.json()['data']
        forged = client.patch(f'/api/inquiry-workspaces/{workspace_id}/artifacts/{record["id"]}', json={'expected_version': record['version'], 'content': {'records': [{'incident_angle_deg': 30, 'reflected_angle_deg': 0}]}})
        assert forged.status_code == 409
        actor.id = 'other'
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}').status_code == 404
        assert client.get(f'/api/inquiry-workspaces/{workspace_id}/runs/{run_id}').status_code == 404
    engine.dispose()


@pytest.mark.parametrize('enabled', [False, True])
def test_feature_flag_controls_router_and_new_tables(enabled):
    env = os.environ.copy()
    env.update(DATABASE_URL='sqlite:///:memory:', INQUIRY_WORKSPACE_ENABLED='true' if enabled else 'false')
    script = """
from sqlalchemy import inspect
from app.main import app, engine
enabled = %s
assert any(path.startswith('/api/inquiry-workspaces') for path in app.openapi()['paths']) == enabled
assert ('workspace_workspaces' in inspect(engine).get_table_names()) == enabled
""" % enabled
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr

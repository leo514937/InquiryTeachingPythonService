from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import UserWorkspaceRoleModel
from app.workspace.api import router
from app.workspace.artifacts.service import _create_artifact, update_artifact
from app.workspace.models import Artifact, ArtifactDependency, Workspace, WorkspaceBase


@pytest.fixture
def canvas():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    WorkspaceBase.metadata.create_all(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([UserWorkspaceRoleModel(user_id=uid, role_category='teacher', created_at='now') for uid in ('teacher', 'other')])
        db.add(Workspace(id='ws', owner_user_id='teacher', title='光的反射', created_at='now', revision=0))
        db.commit()
        first = _create_artifact(db, 'ws', 'LearningGoal', {'title': '一'}, author_kind='agent')
        second = _create_artifact(db, 'ws', 'LearningGoal', {'title': '二'}, author_kind='agent')
        activity = _create_artifact(db, 'ws', 'InquiryActivity', {'title': '活动'}, author_kind='agent')
        db.add(ArtifactDependency(workspace_id='ws', upstream_id=first.id, upstream_version=1, upstream_field='/title', downstream_id=activity.id, downstream_field=''))
        db.commit()
        ids = (first.id, second.id, activity.id)
    actor = SimpleNamespace(id='teacher', user_role='teacher')
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        yield client, engine, actor, ids
    engine.dispose()


def test_order_persists_and_rejects_stale_revision_and_other_owner(canvas):
    client, _, actor, (first, second, _) = canvas
    initial = client.get('/api/inquiry-workspaces/ws').json()['data']
    response = client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': initial['revision'], 'artifact_ids': [second, first]})
    assert response.status_code == 200
    result = client.get('/api/inquiry-workspaces/ws').json()['data']
    assert [item['id'] for item in result['artifacts'] if item['type'] == 'LearningGoal'] == [second, first]
    assert client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': initial['revision'], 'artifact_ids': [first, second]}).status_code == 409
    actor.id = 'other'
    assert client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': result['revision'], 'artifact_ids': [first, second]}).status_code == 404


def test_order_handles_legacy_duplicate_indices(canvas):
    client, engine, _, (first, second, _) = canvas
    with Session(engine) as db:
        db.get(Artifact, first).order_index = 0
        db.get(Artifact, second).order_index = 0
        db.commit()
    desired = sorted([first, second], reverse=True)
    initial = client.get('/api/inquiry-workspaces/ws').json()['data']
    result = client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': initial['revision'], 'artifact_ids': desired})
    assert result.status_code == 200
    after = client.get('/api/inquiry-workspaces/ws').json()['data']['artifacts']
    assert [item['id'] for item in after if item['type'] == 'LearningGoal'] == desired


def test_order_changes_future_report_but_not_existing_snapshot(canvas):
    client, _, _, (first, second, _) = canvas
    snapshot = client.post('/api/inquiry-workspaces/ws/report/snapshots').json()['data']['id']
    previous = client.get(f'/api/inquiry-workspaces/ws/report/snapshots/{snapshot}/print').json()['data']
    revision = client.get('/api/inquiry-workspaces/ws').json()['data']['revision']
    assert client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': revision, 'artifact_ids': [second, first]}).status_code == 200
    projected = client.get('/api/inquiry-workspaces/ws/report').json()['data']
    assert [section['title'] for section in projected['sections'][:2]] == ['二', '一']
    assert client.get(f'/api/inquiry-workspaces/ws/report/snapshots/{snapshot}/print').json()['data'] == previous


def test_order_rejects_mixed_groups_and_active_run(canvas):
    from app.workspace.runtime.runs import create_run
    client, engine, _, (first, second, activity) = canvas
    revision = client.get('/api/inquiry-workspaces/ws').json()['data']['revision']
    mixed = client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': revision, 'artifact_ids': [first, activity]})
    assert mixed.status_code == 422
    with Session(engine) as db:
        create_run(db, 'ws', 'teacher', '需求', 'lesson', 'active')
        db.commit()
    response = client.put('/api/inquiry-workspaces/ws/artifacts/order', json={'expected_revision': revision, 'artifact_ids': [second, first]})
    assert response.status_code == 409


def test_dependency_and_preview_respect_revoked_sources(canvas):
    client, engine, _, (first, _, _) = canvas
    with Session(engine) as db:
        db.get(Artifact, first).source_json = '[{"expert_id":"removed","source":"private"}]'
        db.commit()
    assert client.get('/api/inquiry-workspaces/ws/dependencies').status_code == 403
    assert client.get(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan-preview?expected_version=1').status_code == 403


def test_dependencies_and_replan_preview_are_read_only(canvas):
    client, engine, _, (first, _, activity) = canvas
    with Session(engine) as db:
        update_artifact(db, 'ws', first, 1, {'title': '已修改'})
        db.commit()
    response = client.get('/api/inquiry-workspaces/ws/dependencies')
    assert response.status_code == 200
    assert response.json()['data'][0]['downstream_id'] == activity
    with Session(engine) as db:
        before = (db.get(Artifact, activity).status, db.get(Artifact, activity).review_status, db.get(Workspace, 'ws').revision)
    preview = client.get(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan-preview?expected_version=2')
    assert preview.status_code == 200
    assert [target['id'] for target in preview.json()['data']['targets']] == [activity]
    with Session(engine) as db:
        assert (db.get(Artifact, activity).status, db.get(Artifact, activity).review_status, db.get(Workspace, 'ws').revision) == before
    assert client.get(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan-preview?expected_version=1').status_code == 409


def test_replan_rejects_workspace_changed_after_impact_preview(canvas):
    client, engine, _, (first, second, _) = canvas
    with Session(engine) as db:
        update_artifact(db, 'ws', first, 1, {'title': '已修改'})
        db.commit()
    preview = client.get(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan-preview?expected_version=2').json()['data']
    with Session(engine) as db:
        update_artifact(db, 'ws', second, 1, {'title': '并发修改'})
        db.commit()
    response = client.post(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan', json={'expected_version': 2, 'expected_revision': preview['revision'], 'instruction': '更新下游', 'idempotency_key': 'preview-key'})
    assert response.status_code == 409


def test_replan_rejects_agent_changed_target_after_impact_preview(canvas):
    from app.workspace.artifacts.service import _save_version
    client, engine, _, (first, _, activity) = canvas
    with Session(engine) as db:
        update_artifact(db, 'ws', first, 1, {'title': '已修改'})
        db.commit()
    preview = client.get(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan-preview?expected_version=2').json()['data']
    with Session(engine) as db:
        item = db.get(Artifact, activity)
        _save_version(db, item, item.version, {'title': 'Agent 新版本'}, author_kind='agent', increment_revision=False)
        db.commit()
    response = client.post(f'/api/inquiry-workspaces/ws/artifacts/{first}/replan', json={'expected_version': 2, 'expected_revision': preview['revision'], 'preview_fingerprint': preview['fingerprint'], 'instruction': '更新下游', 'idempotency_key': 'agent-key'})
    assert response.status_code == 409

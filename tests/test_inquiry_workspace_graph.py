from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import UserWorkspaceRoleModel
from app.workspace.api import router
from app.workspace.artifacts.service import create_workspace
from app.workspace.models import WorkspaceBase, WorkspaceEvent, WorkspaceNode, WorkspaceRun
from app.workspace.orchestrator.planner import validate_plan
from app.workspace.runtime.runs import create_run, execute_run


@pytest.fixture
def graph():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    WorkspaceBase.metadata.create_all(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add_all([UserWorkspaceRoleModel(user_id=u, role_category='teacher', created_at='now') for u in ('teacher', 'other')])
        workspace = create_workspace(db, 'teacher', '反射')
        run = create_run(db, workspace.id, 'teacher', '目标', 'lesson', 'request')
        workspace_id, run_id = workspace.id, run.id
    actor = SimpleNamespace(id='teacher', user_role='teacher')
    app = FastAPI()
    app.include_router(router)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        yield client, factory, actor, workspace_id, run_id
    engine.dispose()


def test_graph_exposes_real_edges_events_and_safe_summaries(graph):
    client, factory, actor, ws, run_id = graph
    plan = validate_plan({'version': 1, 'goal': '目标', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {'private': 'SECRET'}},
        {'id': 'b', 'capability': 'activity.design@1', 'depends_on': ['a'], 'inputs': {}},
    ]})
    execute_run(factory, run_id, lambda _: plan, lambda n, _: {'summary': n.id, 'artifacts': [], 'sources': []})
    result = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph')
    assert result.status_code == 200
    data = result.json()['data']
    assert {(edge['source'], edge['target']) for edge in data['edges']} == {('a', 'b')}
    assert {n['status'] for n in data['nodes']} == {'succeeded'}
    assert all(n['started_at'] and n['finished_at'] for n in data['nodes'])
    assert 'SECRET' not in result.text
    assert data['event_cursor'] > 0
    events = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/events').text
    assert 'node_started' in events and 'node_succeeded' in events
    assert client.get(f'/api/inquiry-workspaces/{ws}/runs').json()['data']['items'][0]['id'] == run_id
    actor.id = 'other'
    assert client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph').status_code == 404


def test_failed_node_and_unexecuted_descendant_have_truthful_states(graph):
    client, factory, _, ws, run_id = graph
    plan = validate_plan({'version': 1, 'goal': '目标', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {}},
        {'id': 'b', 'capability': 'activity.design@1', 'depends_on': ['a'], 'inputs': {}},
    ]})
    def fail(node, dependencies):
        raise ValueError('secret internal details')
    execute_run(factory, run_id, lambda _: plan, fail)
    result = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph')
    assert result.status_code == 200
    data = result.json()['data']
    states = {node['id']: node['status'] for node in data['nodes']}
    assert states == {'a': 'failed', 'b': 'skipped'}
    assert 'secret internal details' not in result.text
    assert data['status'] == 'failed'



def test_follow_replays_after_cursor_and_closes_on_terminal_run(graph, monkeypatch):
    client, factory, actor, ws, run_id = graph
    import app.workspace.runtime.events as events
    monkeypatch.setattr(events, 'resolve_token_user', lambda db, token: actor)
    plan = validate_plan({'version': 1, 'goal': '目标', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {}},
    ]})
    execute_run(factory, run_id, lambda _: plan, lambda *_: {'summary': 'ok', 'artifacts': [], 'sources': []})
    first = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/events?after=0').text
    import re
    ids = [int(value) for value in re.findall(r'^id: (\d+)$', first, re.M)]
    assert len(ids) >= 2
    follow = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/events?follow=true&after={ids[-2]}')
    assert follow.status_code == 200
    assert f'id: {ids[-1]}' in follow.text and f'id: {ids[-2]}\n' not in follow.text


def test_cancel_marks_queued_nodes_cancelled_and_running_results_discarded(graph):
    from app.workspace.runtime.runs import cancel_run
    _, factory, _, _, run_id = graph
    with factory.begin() as db:
        db.add_all([
            WorkspaceNode(run_id=run_id, node_id='pending', capability='requirements.analyze@1', status='queued'),
            WorkspaceNode(run_id=run_id, node_id='running', capability='activity.design@1', status='running', started_at='now'),
        ])
        db.flush()
        cancel_run(db, run_id)
    with factory() as db:
        nodes = {n.node_id: n for n in db.query(WorkspaceNode).filter_by(run_id=run_id)}
        assert nodes['pending'].status == 'cancelled'
        assert nodes['running'].status == 'result_discarded' and nodes['running'].finished_at is None


def test_history_and_graph_hide_runs_whose_sources_were_revoked(graph):
    import json
    client, factory, _, ws, run_id = graph
    with factory.begin() as db:
        db.add(WorkspaceNode(run_id=run_id, node_id='old', capability='knowledge.retrieve@1', status='succeeded',
            output_json=json.dumps({'sources': [{'expert_id': 'revoked', 'source': 'private'}]})))
    assert client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph').status_code == 403
    assert client.get(f'/api/inquiry-workspaces/{ws}/runs').json()['data']['items'] == []


def test_legacy_result_references_remain_visible_without_inventing_changes(graph):
    import json
    from app.workspace.artifacts.service import _create_artifact
    client, factory, _, ws, run_id = graph
    with factory.begin() as db:
        artifact = _create_artifact(db, ws, 'LearningGoal', {'title': '目标'}, author_kind='agent')
        run = db.get(WorkspaceRun, run_id)
        run.status = 'completed'
        run.plan_json = json.dumps({'version': 1, 'goal': '目标', 'nodes': [
            {'id': 'old', 'capability': 'goals.compose@1', 'depends_on': [], 'inputs': {}}
        ]})
        db.add(WorkspaceNode(run_id=run_id, node_id='old', capability='goals.compose@1',
            status='succeeded', output_json=json.dumps({'sources': [], 'artifact_refs': [{'id': artifact.id, 'version': 1}]})))
        artifact_id = artifact.id
    result = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph').json()['data']['nodes'][0]
    assert result['started_at'] is None and result['change_kind'] is None
    assert result['result_refs'] == [{'id': artifact_id, 'version': 1, 'operation': 'referenced'}]


def test_event_sequence_is_unique_under_concurrent_writers(tmp_path):
    import concurrent.futures
    from app.workspace.runtime.runs import _event
    engine = create_engine(f'sqlite:///{(tmp_path / "events.db").as_posix()}', connect_args={'check_same_thread': False, 'timeout': 30})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '目标')
        run_id = create_run(db, workspace.id, 'teacher', '目标', 'lesson', 'key').id
    def write(index):
        with factory.begin() as db:
            _event(db, run_id, 'node_started', {'node_id': str(index)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(20)))
    with factory() as db:
        sequences = [row.sequence for row in db.query(WorkspaceEvent).filter_by(run_id=run_id).order_by(WorkspaceEvent.sequence)]
        assert sequences == list(range(1, 22))
    engine.dispose()


def test_follow_drains_more_than_one_event_batch(graph, monkeypatch):
    client, factory, actor, ws, run_id = graph
    import app.workspace.runtime.events as events
    from app.workspace.runtime.runs import _event
    monkeypatch.setattr(events, 'resolve_token_user', lambda db, token: actor)
    with factory.begin() as db:
        for i in range(205):
            _event(db, run_id, 'node_started', {'node_id': str(i)})
        db.get(WorkspaceRun, run_id).status = 'completed'
    response = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/events?follow=true&after=0')
    import re
    ids = [int(value) for value in re.findall(r'^id: (\d+)$', response.text, re.M)]
    assert ids == list(range(1, 207))


def test_cancel_racing_a_committed_node_preserves_success(tmp_path):
    import threading
    import time
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun, WorkspaceNode
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, cancel_run
    engine = create_engine(f'sqlite:///{(tmp_path / "cancel_race.db").as_posix()}', connect_args={'check_same_thread': False, 'timeout': 3})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with factory.begin() as db:
        ws = create_workspace(db, 'teacher', '需求')
        run = create_run(db, ws.id, 'teacher', '需求', 'lesson', 'race')
        run.status = 'running'
        db.add(WorkspaceNode(run_id=run.id, node_id='a', capability='goals.compose@1', status='running'))
        run_id = run.id
    locked, release = threading.Event(), threading.Event()
    errors = []
    def commit_node():
        with factory.begin() as db:
            db.execute(update(WorkspaceRun).where(WorkspaceRun.id == run_id).values(event_sequence=WorkspaceRun.event_sequence + 1))
            db.query(WorkspaceNode).filter_by(run_id=run_id, node_id='a').one().status = 'succeeded'
            db.flush()
            locked.set()
            assert release.wait(3)
    def cancel():
        try:
            with factory.begin() as db:
                cancel_run(db, run_id)
        except Exception as exc:
            errors.append(exc)
    writer = threading.Thread(target=commit_node)
    writer.start()
    assert locked.wait(3)
    canceller = threading.Thread(target=cancel)
    canceller.start()
    time.sleep(.2)
    release.set()
    writer.join(3)
    canceller.join(3)
    assert not writer.is_alive() and not canceller.is_alive()
    assert not errors
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'cancelled'
        assert db.query(WorkspaceNode).filter_by(run_id=run_id, node_id='a').one().status == 'succeeded'
    engine.dispose()



def test_event_replay_never_exposes_unapproved_payload_fields(graph):
    from app.workspace.runtime.runs import _event
    client, factory, _, ws, run_id = graph
    with factory.begin() as db:
        _event(db, run_id, 'review_approved', {'user_id':'private-user', 'content':'secret-source', 'status':'completed'})
    response = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/events')
    assert response.status_code == 200
    assert 'event: review_approved' in response.text
    assert 'private-user' not in response.text and 'secret-source' not in response.text



def test_waiting_review_is_run_level_not_a_fabricated_node_state(graph):
    client, factory, _, ws, run_id = graph
    plan = validate_plan({'version': 1, 'goal': '目标', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {}},
    ]})
    execute_run(factory, run_id, lambda _: plan, lambda *_: {'sources': [], 'artifacts': []},
                validate_completion=lambda _: 'waiting_review')
    data = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph').json()['data']
    assert data['status'] == 'waiting_review'
    assert data['nodes'][0]['status'] == 'succeeded'


def test_open_event_stream_stops_when_user_is_revoked(graph, monkeypatch):
    import asyncio
    import app.workspace.runtime.events as events
    _, factory, actor, ws, run_id = graph
    monkeypatch.setattr(events, 'resolve_token_user', lambda db, token: actor)
    class Request:
        async def is_disconnected(self):
            return False
    async def scenario():
        stream = events.follow_events(Request(), factory, 'token', ws, run_id, 0)
        first = await anext(stream)
        assert 'queued' in first
        monkeypatch.setattr(events, 'resolve_token_user', lambda db, token: None)
        revoked = await anext(stream)
        if revoked.startswith(': heartbeat'):
            revoked = await anext(stream)
        assert 'event: access_revoked' in revoked
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    asyncio.run(scenario())


def test_graph_node_exposes_authorized_source_metadata_without_private_content(graph, monkeypatch):
    import json
    import app.workspace.runtime.graph as projection
    client, factory, _, ws, run_id = graph
    monkeypatch.setattr(projection, 'assert_sources_authorized', lambda db, refs: None)
    with factory.begin() as db:
        run = db.get(WorkspaceRun, run_id)
        run.status = 'completed'
        run.plan_json = json.dumps({'version': 1, 'nodes': [{'id': 'rag', 'capability': 'knowledge.retrieve@1', 'depends_on': []}]})
        db.add(WorkspaceNode(run_id=run_id, node_id='rag', capability='knowledge.retrieve@1', status='succeeded', output_json=json.dumps({'sources': [{'expert_id':'physics', 'source':'standard.md', 'text':'PRIVATE EXCERPT'}]})))
    response = client.get(f'/api/inquiry-workspaces/{ws}/runs/{run_id}/graph')
    assert response.status_code == 200
    assert response.json()['data']['nodes'][0]['source_refs'] == [{'expert_id':'physics', 'source':'standard.md'}]
    assert 'PRIVATE EXCERPT' not in response.text

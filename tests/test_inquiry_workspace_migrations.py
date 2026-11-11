import pytest
from sqlalchemy import create_engine, inspect, text

from app.workspace.migrations import ensure_workspace_schema


def test_additive_migration_preserves_legacy_artifacts():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE workspace_artifacts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, type TEXT NOT NULL, version INTEGER NOT NULL, content_json TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO workspace_artifacts VALUES ('a', 'w', 'Experiment', 1, '{}')"))
    ensure_workspace_schema(engine)
    ensure_workspace_schema(engine)
    columns = {item['name'] for item in inspect(engine).get_columns('workspace_artifacts')}
    assert {'parent_id', 'order_index', 'status', 'locked', 'review_status', 'source_json'}.issubset(columns)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT id, version FROM workspace_artifacts')).all() == [('a', 1)]
    assert 'workspace_runs' in inspect(engine).get_table_names()
    engine.dispose()


def test_unrecognized_legacy_structure_fails_without_rebuilding():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE workspace_artifacts (id TEXT PRIMARY KEY, mystery TEXT)'))
        conn.execute(text("INSERT INTO workspace_artifacts VALUES ('a', 'keep')"))
    with pytest.raises(RuntimeError, match='workspace_artifacts'):
        ensure_workspace_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT mystery FROM workspace_artifacts')).scalar_one() == 'keep'
    assert 'workspace_runs' not in inspect(engine).get_table_names()
    engine.dispose()


def test_migration_restores_unique_record_parent_for_legacy_table():
    from sqlalchemy.exc import IntegrityError
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE workspace_artifacts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, type TEXT NOT NULL, version INTEGER NOT NULL, content_json TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO workspace_artifacts VALUES ('experiment', 'w', 'Experiment', 1, '{}')"))
        conn.execute(text('INSERT INTO workspace_artifacts VALUES (:id, :ws, :type, 1, :content)'), {'id': 'record', 'ws': 'w', 'type': 'DataRecord', 'content': '{"experiment_id":"experiment"}'})
    ensure_workspace_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT parent_id FROM workspace_artifacts WHERE id='record'")).scalar_one() == 'experiment'
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO workspace_artifacts (id, workspace_id, type, parent_id, version, content_json) VALUES ('duplicate', 'w', 'DataRecord', 'experiment', 1, '{}')"))
    engine.dispose()


def test_migration_reconstructs_active_run_reservation():
    from app.workspace.models import WorkspaceBase, WorkspaceActiveRun
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    WorkspaceActiveRun.__table__.drop(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspace_runs (id, workspace_id, owner_user_id, request_key, goal, mode, status, plan_json, error, cancel_requested, input_revision, replan_json, created_at, updated_at) VALUES ('r', 'w', 't', 'k', 'g', 'lesson', 'running', '{}', '', 0, 0, '{}', 'now', 'now')"))
    ensure_workspace_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT workspace_id, run_id FROM workspace_active_runs')).all() == [('w', 'r')]
    engine.dispose()

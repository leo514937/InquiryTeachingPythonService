"""Additive migration for the independent workspace metadata."""
from sqlalchemy import inspect, text
import json

from app.workspace.models import WorkspaceBase


_REQUIRED = {
    'workspace_workspaces': {'id', 'owner_user_id', 'title', 'created_at'},
    'workspace_artifacts': {'id', 'workspace_id', 'type', 'version', 'content_json'},
    'workspace_artifact_versions': {'id', 'artifact_id', 'version', 'content_json', 'created_at'},
    'workspace_record_requests': {'id', 'workspace_id', 'experiment_id', 'request_key', 'artifact_id', 'angle'},
    'workspace_report_snapshots': {'id', 'workspace_id', 'content_json', 'content_hash', 'created_at'},
    'workspace_settings': {'key', 'value_json'},
    'workspace_rag_audits': {'id', 'workspace_id', 'run_id', 'user_id', 'expert_id', 'query', 'allowed_sources_json', 'hit_sources_json', 'chunk_ids_json', 'status', 'created_at'},
    'workspace_runs': {'id', 'workspace_id', 'owner_user_id', 'request_key', 'goal', 'mode', 'status', 'plan_json', 'error', 'cancel_requested', 'lease_owner', 'lease_until', 'created_at', 'updated_at'},
    'workspace_nodes': {'id', 'run_id', 'node_id', 'capability', 'depends_json', 'inputs_json', 'output_json', 'status', 'attempts'},
    'workspace_events': {'id', 'run_id', 'sequence', 'kind', 'data_json', 'created_at'},
    'workspace_dependencies': {'id', 'workspace_id', 'upstream_id', 'upstream_version', 'upstream_field', 'downstream_id', 'downstream_field'},
    'workspace_active_runs': {'workspace_id', 'run_id'},
}
_ADDITIONS = {
    'workspace_workspaces': {'revision': 'INTEGER NOT NULL DEFAULT 0'},
    'workspace_artifacts': {'parent_id': 'VARCHAR', 'order_index': 'INTEGER NOT NULL DEFAULT 0',
                            'status': "VARCHAR NOT NULL DEFAULT 'active'", 'locked': 'INTEGER NOT NULL DEFAULT 0',
                            'review_status': "VARCHAR NOT NULL DEFAULT 'unreviewed'", 'source_json': "TEXT NOT NULL DEFAULT '[]'",
                            'change_paths_json': "TEXT NOT NULL DEFAULT '[]'"},
    'workspace_artifact_versions': {'source_json': "TEXT NOT NULL DEFAULT '[]'", 'author_kind': "VARCHAR NOT NULL DEFAULT 'teacher'", 'run_id': 'VARCHAR', 'run_refs_json': "TEXT NOT NULL DEFAULT '[]'"},
    'workspace_runs': {'input_revision': 'INTEGER NOT NULL DEFAULT 0', 'replan_json': "TEXT NOT NULL DEFAULT '{}'", 'context_json': "TEXT NOT NULL DEFAULT '{}'", 'event_sequence': 'INTEGER NOT NULL DEFAULT 0'},
    'workspace_nodes': {'started_at': 'VARCHAR', 'finished_at': 'VARCHAR', 'error_code': 'VARCHAR', 'changes_json': "TEXT NOT NULL DEFAULT '[]'"},
}


def ensure_workspace_schema(engine):
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    columns = {}
    for table, required in _REQUIRED.items():
        if table in existing:
            columns[table] = {item['name'] for item in inspector.get_columns(table)}
            if not required.issubset(columns[table]):
                raise RuntimeError(f'Unrecognized workspace schema: {table}')
    backfill = []
    active_runs = {}
    with engine.connect() as conn:
        if 'workspace_runs' in existing:
            for workspace_id, run_id in conn.execute(text("SELECT workspace_id, id FROM workspace_runs WHERE cancel_requested=0 AND status IN ('queued','planning','running','waiting_review')")):
                if workspace_id in active_runs:
                    raise RuntimeError('Unrecognized workspace schema: multiple active runs')
                active_runs[workspace_id] = run_id
        if 'workspace_active_runs' in existing:
            for workspace_id, run_id in conn.execute(text('SELECT workspace_id, run_id FROM workspace_active_runs')):
                if active_runs.get(workspace_id) != run_id:
                    raise RuntimeError('Unrecognized workspace schema: active run reservation')
    if 'workspace_artifacts' in existing:
        with engine.connect() as conn:
            if 'parent_id' in columns['workspace_artifacts']:
                duplicates = conn.execute(text("SELECT 1 FROM workspace_artifacts WHERE parent_id IS NOT NULL GROUP BY workspace_id, type, parent_id HAVING COUNT(*) > 1 LIMIT 1")).first()
                if duplicates:
                    raise RuntimeError('Unrecognized workspace schema: duplicate artifact parents')
            else:
                records = conn.execute(text("SELECT id, workspace_id, content_json FROM workspace_artifacts WHERE type='DataRecord'")).all()
                seen = set()
                for record_id, workspace_id, content_json in records:
                    try:
                        parent_id = json.loads(content_json)['experiment_id']
                    except (KeyError, TypeError, ValueError) as exc:
                        raise RuntimeError('Unrecognized workspace schema: record parent') from exc
                    parent = conn.execute(text("SELECT 1 FROM workspace_artifacts WHERE id=:id AND workspace_id=:workspace AND type='Experiment'"), {'id': parent_id, 'workspace': workspace_id}).first()
                    if not isinstance(parent_id, str) or not parent or (workspace_id, parent_id) in seen:
                        raise RuntimeError('Unrecognized workspace schema: record parent')
                    seen.add((workspace_id, parent_id))
                    backfill.append({'id': record_id, 'parent': parent_id})
    with engine.begin() as conn:
        for table, additions in _ADDITIONS.items():
            if table in existing:
                for name, sql_type in additions.items():
                    if name not in columns[table]:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))
        for item in backfill:
            conn.execute(text('UPDATE workspace_artifacts SET parent_id=:parent WHERE id=:id'), item)
        WorkspaceBase.metadata.create_all(bind=conn)
        conn.execute(text('UPDATE workspace_runs SET event_sequence=(SELECT COALESCE(MAX(sequence), 0) FROM workspace_events WHERE workspace_events.run_id=workspace_runs.id) WHERE event_sequence < (SELECT COALESCE(MAX(sequence), 0) FROM workspace_events WHERE workspace_events.run_id=workspace_runs.id)'))
        for version_id, run_id, refs_json in conn.execute(text('SELECT id, run_id, run_refs_json FROM workspace_artifact_versions')):
            try:
                refs = json.loads(refs_json)
                if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                    raise ValueError('invalid run references')
            except (TypeError, ValueError) as exc:
                raise RuntimeError('Unrecognized workspace schema: artifact run references') from exc
            if run_id and run_id not in refs:
                refs.append(run_id)
                conn.execute(text('UPDATE workspace_artifact_versions SET run_refs_json=:refs WHERE id=:id'), {'refs': json.dumps(refs), 'id': version_id})
        for workspace_id, run_id in active_runs.items():
            present = conn.execute(text('SELECT 1 FROM workspace_active_runs WHERE workspace_id=:workspace'), {'workspace': workspace_id}).first()
            if not present:
                conn.execute(text('INSERT INTO workspace_active_runs (workspace_id, run_id) VALUES (:workspace, :run)'), {'workspace': workspace_id, 'run': run_id})
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_workspace_artifact_parent_unique ON workspace_artifacts (workspace_id, type, parent_id)'))

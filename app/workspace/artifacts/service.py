import datetime as dt
import json
import uuid

from sqlalchemy import func, update

from app.workspace.models import Artifact, ArtifactVersion, RecordRequest, Workspace


def _id(prefix):
    return f'{prefix}_{uuid.uuid4().hex}'


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def create_workspace(db, owner_user_id, title):
    row = Workspace(id=_id('ws'), owner_user_id=owner_user_id, title=title, created_at=_now())
    db.add(row)
    db.flush()
    return row


def _create_artifact(db, workspace_id, kind, content, parent_id=None, sources=None, author_kind='teacher', run_id=None, artifact_id=None):
    order_index = (db.query(func.max(Artifact.order_index)).filter_by(workspace_id=workspace_id).scalar() or 0) + 1
    source_json = _json(sources or [])
    row = Artifact(id=artifact_id or _id('art'), workspace_id=workspace_id, type=kind, parent_id=parent_id, order_index=order_index, version=1, content_json=_json(content), source_json=source_json)
    db.add(row)
    db.add(ArtifactVersion(artifact_id=row.id, version=1, content_json=row.content_json, created_at=_now(), source_json=source_json, author_kind=author_kind, run_id=run_id, run_refs_json=_json([run_id] if run_id else [])))
    if author_kind == 'teacher':
        db.execute(update(Workspace).where(Workspace.id == workspace_id).values(revision=Workspace.revision + 1))
    db.flush()
    return row


def create_experiment(db, workspace_id):
    return _create_artifact(db, workspace_id, 'Experiment', {
        'title': '光的反射交互实验', 'component_type': 'light_reflection_v1',
        'component_config': {'initial_incident_angle_deg': 30, 'show_angle_labels': True},
    })


def _save_version(db, row, expected_version, content, sources=None, author_kind='teacher', run_id=None, increment_revision=True, extra_run_refs=None):
    from app.workspace.artifacts.dependencies import changed_fields, mark_affected
    paths = changed_fields(row.content, content)
    current_version = db.query(ArtifactVersion).filter_by(artifact_id=row.id, version=expected_version).first()
    run_refs = json.loads(current_version.run_refs_json) if current_version else []
    if current_version and current_version.run_id and current_version.run_id not in run_refs:
        run_refs.append(current_version.run_id)
    for ref in (extra_run_refs or []) + ([run_id] if run_id else []):
        if ref and ref not in run_refs:
            run_refs.append(ref)
    if run_id is None and current_version is not None:
        run_id = current_version.run_id
    serialized = _json(content)
    source_json = _json(sources) if sources is not None else row.source_json
    changed = db.execute(update(Artifact).where(
        Artifact.id == row.id, Artifact.workspace_id == row.workspace_id,
        Artifact.version == expected_version,
    ).values(version=expected_version + 1, content_json=serialized, source_json=source_json,
             change_paths_json=_json(sorted(paths))), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        raise ValueError('version conflict')
    db.add(ArtifactVersion(artifact_id=row.id, version=expected_version + 1, content_json=serialized, created_at=_now(), source_json=source_json, author_kind=author_kind, run_id=run_id, run_refs_json=_json(run_refs)))
    if increment_revision:
        db.execute(update(Workspace).where(Workspace.id == row.workspace_id).values(revision=Workspace.revision + 1))
    db.flush()
    db.refresh(row)
    mark_affected(db, row.workspace_id, row.id, paths)
    return row


def record_reflection(db, workspace_id, experiment_id, angle, expected_version, key):
    if isinstance(angle, bool) or not isinstance(angle, int) or not 0 <= angle <= 80:
        raise ValueError('incident angle must be an integer from 0 to 80')
    if not key or len(key) > 128:
        raise ValueError('invalid idempotency key')
    experiment = db.query(Artifact).filter_by(id=experiment_id, workspace_id=workspace_id, type='Experiment').first()
    if not experiment or experiment.content.get('component_type') != 'light_reflection_v1':
        raise LookupError('experiment not found')
    previous = db.query(RecordRequest).filter_by(workspace_id=workspace_id, experiment_id=experiment_id, request_key=key).first()
    if previous:
        if previous.angle != angle:
            raise ValueError('idempotency key reused')
        return db.query(Artifact).filter_by(id=previous.artifact_id, workspace_id=workspace_id).one()
    row = db.query(Artifact).filter_by(workspace_id=workspace_id, type='DataRecord', parent_id=experiment_id).first()
    entry = {'id': _id('rec'), 'incident_angle_deg': angle, 'reflected_angle_deg': angle, 'created_at': _now(), 'experiment_version': experiment.version}
    if row is None:
        if expected_version is not None:
            raise ValueError('version conflict')
        row = _create_artifact(db, workspace_id, 'DataRecord', {'experiment_id': experiment_id, 'records': [entry], 'conclusion': ''}, parent_id=experiment_id, sources=json.loads(experiment.source_json))
    else:
        if expected_version != row.version:
            raise ValueError('version conflict')
        content = row.content
        content['records'].append(entry)
        combined = json.loads(row.source_json) + json.loads(experiment.source_json)
        sources = list({(item['expert_id'], item['source']): item for item in combined}.values())
        row = _save_version(db, row, expected_version, content, sources=sources)
    db.add(RecordRequest(workspace_id=workspace_id, experiment_id=experiment_id, request_key=key, artifact_id=row.id, angle=angle))
    db.flush()
    return row


def update_observation(db, workspace_id, artifact_id, expected_version, conclusion):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id, type='DataRecord').first()
    if not row:
        raise LookupError('record not found')
    content = row.content
    content['conclusion'] = conclusion
    return _save_version(db, row, expected_version, content)


def include_reflection_in_report(db, workspace_id, artifact_id, expected_version, include):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id, type='DataRecord').first()
    if not row:
        raise LookupError('record not found')
    content = row.content
    content['include_in_report'] = include
    return _save_version(db, row, expected_version, content)


def delete_reflection_record(db, workspace_id, artifact_id, expected_version, record_id):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id, type='DataRecord').first()
    if not row:
        raise LookupError('record not found')
    content = row.content
    kept = [item for item in content['records'] if item['id'] != record_id]
    if len(kept) == len(content['records']):
        raise LookupError('observation not found')
    content['records'] = kept
    return _save_version(db, row, expected_version, content)


def update_artifact(db, workspace_id, artifact_id, expected_version, content):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if not row:
        raise LookupError('artifact not found')
    if row.type == 'DataRecord':
        raise ValueError('实验记录只能通过记录接口修改')
    if row.type == 'LessonDocument':
        raise ValueError('教案只能通过教案接口修改')
    if not isinstance(content, dict):
        raise ValueError('content must be an object')
    if row.type == 'Experiment' and content.get('component_type') not in (None, '', 'light_reflection_v1'):
        raise ValueError('unknown component')
    current = db.query(ArtifactVersion).filter_by(artifact_id=row.id, version=row.version).first()
    if current and current.run_id:
        from app.workspace.models import WorkspaceRun
        run = db.get(WorkspaceRun, current.run_id)
        if run and json.loads(run.context_json or '{}').get('studio_mode'):
            if row.locked:
                raise ValueError('教学成果已锁定')
            for field in ('goal_ids', 'activity_ids', 'minutes'):
                if content.get(field) != row.content.get(field):
                    raise ValueError('不能直接修改关联或活动时间，请重新设计')
    return _save_version(db, row, expected_version, content)


def confirm_artifact_review(db, workspace_id, artifact_id, expected_version):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if not row:
        raise LookupError('artifact not found')
    if row.status != 'stale' and row.review_status != 'needs_review':
        raise ValueError('当前成果无需检查')
    result = _save_version(db, row, expected_version, row.content)
    result.status = 'active'
    result.review_status = 'unreviewed'
    db.flush()
    return result


def restore_artifact(db, workspace_id, artifact_id, expected_version, version):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if not row:
        raise LookupError('artifact not found')
    if row.type == 'LessonDocument' and row.locked:
        raise ValueError('教案已锁定')
    previous = db.query(ArtifactVersion).filter_by(artifact_id=artifact_id, version=version).first()
    if not previous:
        raise LookupError('artifact version not found')
    from app.workspace.integrations.rag import assert_sources_authorized
    combined = json.loads(row.source_json) + json.loads(previous.source_json)
    sources = list({(item['expert_id'], item['source']): item for item in combined}.values())
    assert_sources_authorized(db, sources)
    previous_refs = json.loads(previous.run_refs_json)
    if previous.run_id and previous.run_id not in previous_refs:
        previous_refs.append(previous.run_id)
    return _save_version(db, row, expected_version, json.loads(previous.content_json), sources=sources, extra_run_refs=previous_refs)


def set_artifact_lock(db, workspace_id, artifact_id, expected_version, locked):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if not row:
        raise LookupError('artifact not found')
    row = _save_version(db, row, expected_version, row.content)
    row.locked = int(locked)
    db.flush()
    return row

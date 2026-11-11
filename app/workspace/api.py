from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from fastapi.responses import Response, StreamingResponse
from io import BytesIO
from urllib.parse import quote
import json
import hashlib

from app.core.auth import get_current_user, get_admin_user
from app.db.database import get_db
from app.db.models import UserModel
from app.services.session_access_service import resolve_workspace_role
from app.workspace.artifacts.service import create_experiment, create_workspace, record_reflection, update_observation, include_reflection_in_report, delete_reflection_record, update_artifact, restore_artifact, set_artifact_lock
from app.workspace.models import Artifact, ArtifactDependency, ArtifactVersion, Workspace, WorkspaceActiveRun, WorkspaceEvent, WorkspaceNode, WorkspaceRun
from app.workspace.runtime.runs import create_run, create_replan_run, cancel_run, _event
from app.core.sse import format_sse
from app.workspace.reports.service import create_narrative, update_narrative, project_report, create_snapshot, read_snapshot
from app.workspace.integrations.rag import get_allowed_experts, set_allowed_experts, assert_sources_authorized


router = APIRouter(prefix='/api/inquiry-workspaces', tags=['inquiry-workspaces'])


class CreateWorkspace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=4000)


class RecordInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    angle: StrictInt = Field(ge=0, le=80)
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    conclusion: str = Field(max_length=10000)


class ArtifactUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    content: dict


class ArtifactRestore(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    version: int = Field(ge=1)


class ReplanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    expected_revision: int | None = Field(default=None, ge=0)
    preview_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    instruction: str = Field(default='', max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ArtifactLock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    locked: bool


class ArtifactOrder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    artifact_ids: list[str] = Field(min_length=1, max_length=500)


class NarrativeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    paragraphs: list[str] = Field(max_length=100)


class ReportSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    include: bool


class NarrativeUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    paragraphs: list[str] = Field(max_length=100)


class ExpertSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expert_ids: list[str] = Field(max_length=20)


from app.workspace.context import TeachingContext


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str = Field(min_length=1, max_length=4000)
    mode: Literal['lesson', 'experiment'] = 'lesson'
    idempotency_key: str = Field(min_length=1, max_length=128)
    teaching_context: TeachingContext | None = None


class RunApproval(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['approve']
    note: str = Field(default='', max_length=2000)


def _owned(db, user, workspace_id):
    resolve_workspace_role(db, user, 'teacher')
    row = db.query(Workspace).filter_by(id=workspace_id, owner_user_id=user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail='Workspace not found')
    return row


def _artifact(row):
    return {'id': row.id, 'type': row.type, 'version': row.version, 'content': row.content,
            'source_refs': json.loads(row.source_json), 'locked': bool(row.locked), 'review_status': row.review_status,
            'order_index': row.order_index, 'status': row.status}


def _guard_artifacts(db, workspace_id, artifact_id=None):
    query = db.query(Artifact).filter_by(workspace_id=workspace_id)
    if artifact_id is not None:
        query = query.filter_by(id=artifact_id)
    for artifact in query.all():
        assert_sources_authorized(db, json.loads(artifact.source_json))


@router.get('')
def list_workspaces(db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    resolve_workspace_role(db, user, 'teacher')
    rows = db.query(Workspace).filter_by(owner_user_id=user.id).order_by(Workspace.created_at.desc()).all()
    return {'data': [{'id': row.id, 'title': row.title, 'created_at': row.created_at} for row in rows]}


@router.get('/admin/settings')
def get_settings(db: Session = Depends(get_db), user: UserModel = Depends(get_admin_user)):
    return {'data': {'expert_ids': get_allowed_experts(db)}}


@router.put('/admin/settings')
def put_settings(payload: ExpertSettings, db: Session = Depends(get_db), user: UserModel = Depends(get_admin_user)):
    try:
        experts = set_allowed_experts(db, payload.expert_ids)
        db.commit()
        return {'data': {'expert_ids': experts}}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('')
def add_workspace(payload: CreateWorkspace, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    resolve_workspace_role(db, user, 'teacher')
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail='请输入教学需求')
    row = create_workspace(db, user.id, title)
    db.commit()
    return {'data': {'id': row.id, 'title': row.title, 'created_at': row.created_at}}


@router.get('/{workspace_id}')
def get_workspace(workspace_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    row = _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    artifacts = db.query(Artifact).filter_by(workspace_id=row.id).order_by(Artifact.order_index, Artifact.id).all()
    latest = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id, owner_user_id=user.id).order_by(WorkspaceRun.created_at.desc()).first()
    if latest:
        _owned_run(db, user, workspace_id, latest.id)
    return {'data': {'id': row.id, 'title': row.title, 'revision': row.revision, 'artifacts': [_artifact(item) for item in artifacts],
                     'latest_run': _run_data(db, latest) if latest else None}}


_ORDER_GROUPS = {'LearningGoal': 'goals', 'InquiryQuestion': 'questions', 'KnowledgeCard': 'knowledge',
                 'Experiment': 'activities', 'InquiryActivity': 'activities', 'Assessment': 'assessment'}
from app.workspace.artifacts.types import ACTIVITY_TYPES
_ORDER_GROUPS.update({kind: 'activities' for kind in ACTIVITY_TYPES})


@router.put('/{workspace_id}/artifacts/order')
def order_artifacts(workspace_id: str, payload: ArtifactOrder, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    ids = payload.artifact_ids
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail='对象不能重复')
    rows = db.query(Artifact).filter(Artifact.workspace_id == workspace_id, Artifact.id.in_(ids)).all()
    groups = {_ORDER_GROUPS.get(row.type) for row in rows}
    if len(rows) != len(ids) or len(groups) != 1 or None in groups:
        raise HTTPException(status_code=422, detail='只能排序同组教学对象')
    group = next(iter(groups))
    all_group = [row for row in db.query(Artifact).filter_by(workspace_id=workspace_id).all() if _ORDER_GROUPS.get(row.type) == group]
    if {row.id for row in all_group} != set(ids):
        raise HTTPException(status_code=409, detail='对象列表已更改，请刷新')
    active = db.query(WorkspaceActiveRun).filter_by(workspace_id=workspace_id).exists()
    changed = db.execute(update(Workspace).where(Workspace.id == workspace_id, Workspace.revision == payload.expected_revision, ~active)
                         .values(revision=Workspace.revision + 1), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail='工作空间已更改或运行中，请刷新')
    by_id = {row.id: row for row in rows}
    for index, artifact_id in enumerate(ids, start=1):
        by_id[artifact_id].order_index = index
    db.commit()
    return {'data': {'revision': payload.expected_revision + 1}}


@router.get('/{workspace_id}/dependencies')
def dependencies(workspace_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    rows = db.query(ArtifactDependency).filter_by(workspace_id=workspace_id).all()
    return {'data': [{'upstream_id': r.upstream_id, 'upstream_version': r.upstream_version,
                      'upstream_field': r.upstream_field, 'downstream_id': r.downstream_id,
                      'downstream_field': r.downstream_field} for r in rows]}


@router.get('/{workspace_id}/artifacts/{artifact_id}/replan-preview')
def replan_preview(workspace_id: str, artifact_id: str, expected_version: int = Query(..., ge=1), db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    from app.workspace.runtime.replan import prepare_replan
    workspace = _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    try:
        result = prepare_replan(db, workspace_id, artifact_id, mark_review=False)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result['root']['version'] != expected_version:
        raise HTTPException(status_code=409, detail='对象已更改，请刷新')
    return {'data': {'revision': workspace.revision, 'fingerprint': _replan_fingerprint(db, workspace_id, result), 'targets': [{'id': row['id'], 'version': row['version'], 'type': row['type']} for row in result['targets']],
                     'requires_review': result['requires_review']}}


def _replan_fingerprint(db, workspace_id, result):
    ids = [row['id'] for row in result['targets']] + result['requires_review']
    rows = db.query(Artifact).filter(Artifact.workspace_id == workspace_id, Artifact.id.in_(ids)).all()
    snapshot = {'root': [result['root']['id'], result['root']['version']],
                'targets': sorted((row['id'], row['version']) for row in result['targets']),
                'review': sorted(result['requires_review']),
                'objects': sorted((row.id, row.version, row.status, row.review_status, row.locked) for row in rows),
                'edges': sorted((edge['upstream_id'], edge['downstream_id']) for edge in result['edges'])}
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _owned_run(db, user, workspace_id, run_id):
    _owned(db, user, workspace_id)
    row = db.query(WorkspaceRun).filter_by(id=run_id, workspace_id=workspace_id, owner_user_id=user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail='Run not found')
    from app.workspace.runtime.graph import assert_run_sources
    assert_run_sources(db, row)
    return row


def _run_data(db, row):
    from app.workspace.orchestrator.evaluator import risk_only_review
    nodes = db.query(WorkspaceNode).filter_by(run_id=row.id).order_by(WorkspaceNode.id).all()
    return {'id': row.id, 'status': row.status, 'error': row.error, 'mode': row.mode,
            'teaching_context': TeachingContext.from_request(row.goal, json.loads(row.context_json or '{}')).model_dump(mode='json'),
            'review_approvable': row.status == 'waiting_review' and risk_only_review(row.error),
            'nodes': [{'id': n.node_id, 'capability': n.capability, 'status': n.status, 'attempts': n.attempts} for n in nodes],
            'warnings': [w for n in nodes if n.status == 'succeeded' for w in json.loads(n.output_json).get('warnings', [])]}



@router.get('/{workspace_id}/runs')
def list_runs(workspace_id: str, limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
              db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    import base64
    from sqlalchemy import and_, or_
    from app.workspace.runtime.graph import assert_run_sources
    _owned(db, user, workspace_id)
    boundary = None
    if cursor:
        try:
            boundary = json.loads(base64.urlsafe_b64decode(cursor.encode('ascii')).decode('utf-8'))
            if not isinstance(boundary, list) or len(boundary) != 2 or not all(isinstance(x, str) for x in boundary):
                raise ValueError()
        except Exception as exc:
            raise HTTPException(status_code=422, detail='无效的分页游标') from exc
    result = []
    while len(result) <= limit:
        query = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id, owner_user_id=user.id)
        if boundary:
            query = query.filter(or_(WorkspaceRun.created_at < boundary[0],
                                     and_(WorkspaceRun.created_at == boundary[0], WorkspaceRun.id < boundary[1])))
        batch = query.order_by(WorkspaceRun.created_at.desc(), WorkspaceRun.id.desc()).limit(100).all()
        if not batch:
            break
        for row in batch:
            boundary = [row.created_at, row.id]
            try:
                assert_run_sources(db, row)
            except HTTPException as exc:
                if exc.status_code == 403:
                    continue
                raise
            result.append(row)
            if len(result) > limit:
                break
        if len(batch) < 100:
            break
    page = result[:limit]
    next_cursor = None
    if len(result) > limit and page:
        next_cursor = base64.urlsafe_b64encode(json.dumps([page[-1].created_at, page[-1].id]).encode('utf-8')).decode('ascii')
    return {'data': {'items': [{'id': r.id, 'mode': r.mode, 'status': r.status,
                               'created_at': r.created_at, 'updated_at': r.updated_at} for r in page],
                     'next_cursor': next_cursor}}


@router.get('/{workspace_id}/runs/{run_id}/graph')
def run_graph(workspace_id: str, run_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    from app.workspace.runtime.graph import consistent_graph
    _owned_run(db, user, workspace_id, run_id)
    return {'data': consistent_graph(db, run_id)}


@router.get('/{workspace_id}/runs/{run_id}/nodes/{node_id}')
def run_node(workspace_id: str, run_id: str, node_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    from app.workspace.runtime.graph import consistent_graph
    _owned_run(db, user, workspace_id, run_id)
    graph = consistent_graph(db, run_id)
    node = next((item for item in graph['nodes'] if item['id'] == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail='节点不存在')
    return {'data': node}


@router.post('/{workspace_id}/runs')
def add_run(workspace_id: str, payload: RunInput, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    try:
        row = create_run(db, workspace_id, user.id, payload.goal.strip(), payload.mode, payload.idempotency_key, payload.teaching_context.model_dump(exclude_unset=True) if payload.teaching_context else None)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='运行请求冲突') from exc
    return {'data': _run_data(db, row)}


@router.get('/{workspace_id}/runs/{run_id}')
def get_run(workspace_id: str, run_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    return {'data': _run_data(db, _owned_run(db, user, workspace_id, run_id))}


@router.get('/{workspace_id}/runs/{run_id}/events')
def run_events(workspace_id: str, run_id: str, request: Request, after: int = Query(0, ge=0),
               follow: bool = Query(False), last_event_id: str | None = Header(None, alias='Last-Event-ID'),
               db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned_run(db, user, workspace_id, run_id)
    if last_event_id and last_event_id.isdecimal():
        after = max(after, int(last_event_id))
    if follow:
        from sqlalchemy.orm import sessionmaker
        from app.services.auth_service import AUTH_COOKIE_NAME
        from app.workspace.runtime.events import follow_events
        factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        token = request.cookies.get(AUTH_COOKIE_NAME)
        db.close()
        return StreamingResponse(follow_events(request, factory, token, workspace_id, run_id, after),
                                 media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    events = db.query(WorkspaceEvent).filter(WorkspaceEvent.run_id == run_id, WorkspaceEvent.sequence > after).order_by(WorkspaceEvent.sequence).limit(200).all()
    from app.workspace.runtime.events import _safe_event
    body = ''.join(_safe_event(event) for event in events)
    return Response(content=body, media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})


@router.post('/{workspace_id}/runs/{run_id}/cancel')
def stop_run(workspace_id: str, run_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned_run(db, user, workspace_id, run_id)
    row = cancel_run(db, run_id)
    db.commit()
    return {'data': _run_data(db, row)}


@router.post('/{workspace_id}/runs/{run_id}/resume')
def approve_run(workspace_id: str, run_id: str, payload: RunApproval, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    row = _owned_run(db, user, workspace_id, run_id)
    from app.workspace.orchestrator.evaluator import risk_only_review
    if row.status == 'waiting_review' and not risk_only_review(row.error):
        raise HTTPException(status_code=409, detail='教学信息或检查不完整，请补充后重新检查；也可以取消本次运行')
    locked = db.execute(update(Workspace).where(Workspace.id == workspace_id, Workspace.revision == row.input_revision)
                        .values(revision=Workspace.revision), execution_options={'synchronize_session': False})
    if locked.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail='工作空间已变更，请重新检查并运行')
    changed = db.execute(update(WorkspaceRun).where(WorkspaceRun.id == run_id, WorkspaceRun.workspace_id == workspace_id,
                                                    WorkspaceRun.status == 'waiting_review', WorkspaceRun.cancel_requested == 0)
                         .values(status='completed'), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail='当前运行不需要审核')
    _event(db, run_id, 'review_approved', {'user_id': user.id})
    db.query(WorkspaceActiveRun).filter_by(workspace_id=workspace_id, run_id=run_id).delete(synchronize_session=False)
    db.commit()
    row = db.get(WorkspaceRun, run_id)
    db.refresh(row)
    return {'data': _run_data(db, row)}


@router.post('/{workspace_id}/experiments/reflection')
def add_reflection(workspace_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    row = create_experiment(db, workspace_id)
    db.commit()
    return {'data': _artifact(row)}


@router.post('/{workspace_id}/artifacts/{artifact_id}/records')
def add_record(workspace_id: str, artifact_id: str, payload: RecordInput, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = record_reflection(db, workspace_id, artifact_id, payload.angle, payload.expected_version, payload.idempotency_key)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='记录已更改，请刷新后重试') from exc
    return {'data': _artifact(row)}


@router.patch('/{workspace_id}/artifacts/{artifact_id}')
def edit_record(workspace_id: str, artifact_id: str, payload: ObservationInput | ArtifactUpdate, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        if isinstance(payload, ObservationInput):
            row = update_observation(db, workspace_id, artifact_id, payload.expected_version, payload.conclusion)
        else:
            row = update_artifact(db, workspace_id, artifact_id, payload.expected_version, payload.content)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.get('/{workspace_id}/artifacts/{artifact_id}/versions')
def artifact_versions(workspace_id: str, artifact_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    artifact = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail='Artifact not found')
    _guard_artifacts(db, workspace_id, artifact_id)
    versions = db.query(ArtifactVersion).filter_by(artifact_id=artifact_id).order_by(ArtifactVersion.version).all()
    for version in versions:
        assert_sources_authorized(db, json.loads(version.source_json))
    return {'data': [{'version': v.version, 'content': json.loads(v.content_json), 'created_at': v.created_at, 'author_kind': v.author_kind} for v in versions]}


@router.post('/{workspace_id}/artifacts/{artifact_id}/restore')
def restore_version(workspace_id: str, artifact_id: str, payload: ArtifactRestore, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = restore_artifact(db, workspace_id, artifact_id, payload.expected_version, payload.version)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.post('/{workspace_id}/artifacts/{artifact_id}/replan')
def replan_artifact(workspace_id: str, artifact_id: str, payload: ReplanInput, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    try:
        if payload.expected_revision is not None:
            locked = db.execute(update(Workspace).where(Workspace.id == workspace_id, Workspace.revision == payload.expected_revision)
                                .values(revision=Workspace.revision), execution_options={'synchronize_session': False})
            if locked.rowcount != 1:
                raise ValueError('工作空间已更改，请重新预览影响')
        if payload.preview_fingerprint is not None:
            from app.workspace.runtime.replan import prepare_replan
            preview = prepare_replan(db, workspace_id, artifact_id, mark_review=False)
            if _replan_fingerprint(db, workspace_id, preview) != payload.preview_fingerprint:
                raise ValueError('受影响对象已更改，请重新预览影响')
        row = create_replan_run(db, workspace_id, user.id, artifact_id, payload.expected_version,
                                payload.instruction, payload.idempotency_key)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc) if isinstance(exc, ValueError) else '运行请求冲突') from exc
    return {'data': _run_data(db, row)}


@router.put('/{workspace_id}/artifacts/{artifact_id}/lock')
def lock_artifact(workspace_id: str, artifact_id: str, payload: ArtifactLock, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = set_artifact_lock(db, workspace_id, artifact_id, payload.expected_version, payload.locked)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.put('/{workspace_id}/artifacts/{artifact_id}/report-selection')
def select_record_for_report(workspace_id: str, artifact_id: str, payload: ReportSelection, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = include_reflection_in_report(db, workspace_id, artifact_id, payload.expected_version, payload.include)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.delete('/{workspace_id}/artifacts/{artifact_id}/records/{record_id}')
def delete_record(workspace_id: str, artifact_id: str, record_id: str, expected_version: int, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = delete_reflection_record(db, workspace_id, artifact_id, expected_version, record_id)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.post('/{workspace_id}/narratives')
def add_narrative(workspace_id: str, payload: NarrativeInput, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    row = create_narrative(db, workspace_id, payload.section_key, payload.title, payload.paragraphs)
    db.commit()
    return {'data': _artifact(row)}


@router.patch('/{workspace_id}/narratives/{artifact_id}')
def edit_narrative(workspace_id: str, artifact_id: str, payload: NarrativeUpdate, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id, artifact_id)
    try:
        row = update_narrative(db, workspace_id, artifact_id, payload.expected_version, payload.paragraphs)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': _artifact(row)}


@router.get('/{workspace_id}/report')
def get_report(workspace_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    return {'data': project_report(db, workspace_id)}


@router.post('/{workspace_id}/report/snapshots')
def make_snapshot(workspace_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    _guard_artifacts(db, workspace_id)
    try:
        row = create_snapshot(db, workspace_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'data': {'id': row.id, 'created_at': row.created_at, 'content_hash': row.content_hash}}


@router.get('/{workspace_id}/report/snapshots/{snapshot_id}/print')
def snapshot_print(workspace_id: str, snapshot_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _owned(db, user, workspace_id)
    try:
        data = read_snapshot(db, workspace_id, snapshot_id)
        assert_sources_authorized(db, data.get('source_refs', []))
        return {'data': data}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/{workspace_id}/report/snapshots/{snapshot_id}/docx')
def snapshot_docx(workspace_id: str, snapshot_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    from docx import Document

    data = snapshot_print(workspace_id, snapshot_id, db, user)['data']
    document = Document()
    document.add_heading(data['title'], 0)
    document.add_paragraph(data['notice'])
    assumptions = (data.get('teaching_context') or {}).get('assumptions', [])
    if assumptions:
        document.add_heading('待确认的教学条件', 1)
        for assumption in assumptions:
            document.add_paragraph(assumption)
    profile = (data.get('teaching_context') or {}).get('learner_profile')
    if profile:
        document.add_heading('年级适配建议', 1)
        document.add_paragraph('以下建议基于填写的年级，并非对本班学生的实际测评。')
        for key in ('language_guidance', 'task_guidance', 'abstraction_guidance', 'teacher_support', 'collaboration_guidance'):
            document.add_paragraph(profile.get(key, ''))
    for section in data['sections']:
        document.add_heading(section['title'], 1)
        for paragraph in section['paragraphs']:
            document.add_paragraph(paragraph)
        if section.get('student_instructions'):
            document.add_paragraph('学生任务：' + section['student_instructions'])
    output = BytesIO()
    document.save(output)
    return Response(content=output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(data['title'] + '.docx')}"})

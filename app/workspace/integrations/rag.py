from app.services.curriculum_permission_service import CurriculumPermissionService
from app.services.rag_service import RagService
from app.workspace.artifacts.service import _id, _json, _now
from app.workspace.models import WorkspaceRagAudit, WorkspaceSetting
from app.agents.registry import get_agent_registry
import json
from fastapi import HTTPException
from app.db.models import CurriculumSourceModel


def get_allowed_experts(db):
    setting = db.get(WorkspaceSetting, 'allowed_experts')
    return json.loads(setting.value_json) if setting else []


def set_allowed_experts(db, expert_ids):
    registry = get_agent_registry()
    normalized = list(dict.fromkeys(expert_ids))
    if any(registry.selectable_expert(expert_id, 'teacher') is None for expert_id in normalized):
        raise ValueError('仅允许可选择的教师专家')
    setting = db.get(WorkspaceSetting, 'allowed_experts')
    if setting is None:
        setting = WorkspaceSetting(key='allowed_experts', value_json=_json(normalized))
        db.add(setting)
    else:
        setting.value_json = _json(normalized)
    db.flush()
    return normalized


def assert_sources_authorized(db, sources):
    configured = set(get_allowed_experts(db))
    permissions = {}
    if not isinstance(sources, list):
        raise HTTPException(status_code=403, detail='来源权限无法验证')
    for item in sources:
        if not isinstance(item, dict) or not isinstance(item.get('source'), str) or not isinstance(item.get('expert_id'), str):
            raise HTTPException(status_code=403, detail='来源权限无法验证')
        expert_id, source = item['expert_id'], item['source']
        if expert_id not in configured:
            raise HTTPException(status_code=403, detail='来源权限已撤销，请联系管理员或重新生成')
        if expert_id not in permissions:
            permissions[expert_id] = set(filter_curriculum_sources(db, CurriculumPermissionService.allowed_sources(db, expert_id, role_category='teacher')))
        if source not in permissions[expert_id]:
            raise HTTPException(status_code=403, detail='来源权限已撤销，请联系管理员或重新生成')
        if item.get('source_version'):
            current = db.get(CurriculumSourceModel, source)
            if current is None or current.checksum != item['source_version']:
                raise HTTPException(status_code=403, detail='来源版本已变更，请重新生成')


def filter_curriculum_sources(db, sources):
    if not sources:
        return []
    rows = db.query(CurriculumSourceModel.source).filter(
        CurriculumSourceModel.source.in_(sources), CurriculumSourceModel.category == 'curriculum'
    ).all()
    eligible = {str(row[0]) for row in rows}
    return [source for source in sources if source in eligible]


def resolve_selected_sources(db, source_ids):
    """Resolve an explicit selection using one server-selected expert's permissions.

    An empty selection always means no sources. IDs are deliberately checked as
    a set before retrieval so invalid or revoked selections never broaden scope.
    """
    if not isinstance(source_ids, list) or any(not isinstance(item, str) or not item for item in source_ids):
        raise HTTPException(status_code=422, detail='资料选择无效')
    if len(source_ids) > 20 or len(source_ids) != len(set(source_ids)):
        raise HTTPException(status_code=422, detail='资料选择重复或超过上限')
    configured = get_allowed_experts(db)
    expert = configured[0] if configured else ''
    if not source_ids:
        return expert, []
    allowed = set(filter_curriculum_sources(
        db, CurriculumPermissionService.allowed_sources(db, expert, role_category='teacher')
    )) if expert else set()
    rows = db.query(CurriculumSourceModel).filter(CurriculumSourceModel.id.in_(source_ids)).all()
    by_id = {row.id: row for row in rows}
    if any(source_id not in by_id or by_id[source_id].source not in allowed for source_id in source_ids):
        raise HTTPException(status_code=403, detail='所选资料不可用或无权限')
    return expert, [by_id[source_id] for source_id in source_ids]


def retrieve_authorized(db, *, workspace_id, run_id, user_id, expert_id, configured_experts, query, source_scope=None):
    allowed = []
    context = ''
    metadata = {'mode': 'expert_not_configured', 'query': query, 'hit_sources': [], 'records': []}
    if expert_id in configured_experts:
        allowed = filter_curriculum_sources(db, CurriculumPermissionService.allowed_sources(db, expert_id, role_category='teacher'))
        if source_scope is not None:
            allowed = [source for source in allowed if source in set(source_scope)]
        if not allowed:
            metadata['mode'] = 'no_expert_permission'
        else:
            context, metadata = RagService.retrieve_curriculum_context(
                db, topic=query, stage={}, user_message=query, expert_id=expert_id,
                allowed_sources=allowed, role_category='teacher',
            )
            hits = set(metadata.get('hit_sources', []))
            if not hits.issubset(set(allowed)) or any(record.get('source') not in allowed for record in metadata.get('records', [])):
                context = ''
                metadata = {'mode': 'permission_error', 'query': query, 'hit_sources': [], 'records': []}
    db.add(WorkspaceRagAudit(
        id=_id('wsaudit'), workspace_id=workspace_id, run_id=run_id, user_id=user_id,
        expert_id=expert_id, query=query, allowed_sources_json=_json(allowed),
        hit_sources_json=_json(metadata.get('hit_sources', [])),
        chunk_ids_json=_json([r.get('chunk_id') for r in metadata.get('records', [])]),
        status=metadata.get('mode', 'unknown'), created_at=_now(),
    ))
    db.flush()
    return context, metadata


def retrieve_selected_sources(db, *, workspace_id, run_id, user_id, query, source_ids):
    """Retrieve only an explicit selection, using the existing audited boundary."""
    expert, rows = resolve_selected_sources(db, source_ids)
    if not rows:
        return '', {'mode': 'no_sources', 'query': query, 'hit_sources': [], 'records': []}
    return retrieve_authorized(
        db, workspace_id=workspace_id, run_id=run_id, user_id=user_id,
        expert_id=expert, configured_experts=get_allowed_experts(db), query=query,
        source_scope=[row.source for row in rows],
    )

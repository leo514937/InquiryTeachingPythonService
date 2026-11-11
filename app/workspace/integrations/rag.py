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


def filter_curriculum_sources(db, sources):
    if not sources:
        return []
    rows = db.query(CurriculumSourceModel.source).filter(
        CurriculumSourceModel.source.in_(sources), CurriculumSourceModel.category == 'curriculum'
    ).all()
    eligible = {str(row[0]) for row in rows}
    return [source for source in sources if source in eligible]


def retrieve_authorized(db, *, workspace_id, run_id, user_id, expert_id, configured_experts, query):
    allowed = []
    context = ''
    metadata = {'mode': 'expert_not_configured', 'query': query, 'hit_sources': [], 'records': []}
    if expert_id in configured_experts:
        allowed = filter_curriculum_sources(db, CurriculumPermissionService.allowed_sources(db, expert_id, role_category='teacher'))
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

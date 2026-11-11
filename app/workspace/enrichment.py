"""Build a constrained scene context using the existing file-authorized RAG service."""
from app.db.models import CurriculumSourceModel
from app.services.curriculum_permission_service import CurriculumPermissionService
from app.workspace.integrations.rag import filter_curriculum_sources, get_allowed_experts, retrieve_authorized
from app.workspace.scene_catalog import load_catalog, load_scenes, rewrite_queries


class NoEvidence(ValueError):
    """No authorized evidence was found and the teacher did not opt in."""


class SourceForbidden(PermissionError):
    """A selected source is not authorized for the server-selected expert."""


def build_scene_context(db, goal: str, teaching_context: dict, workspace_id: str, run_id: str, user_id: str) -> dict:
    scenes = load_scenes()
    scene_ids = teaching_context.get('scene_ids') or []
    custom_ids = teaching_context.get('custom_source_ids') or []
    if len(scene_ids) > 3 or len(scene_ids) != len(set(scene_ids)) or set(scene_ids) - set(scenes):
        raise ValueError('invalid scenes')
    if custom_ids and 'custom' not in scene_ids:
        raise ValueError('custom sources require custom scene')
    catalog = load_catalog()
    configured = get_allowed_experts(db)
    # One configured expert is selected server-side: permissions are never unioned.
    expert = configured[0] if configured else ''
    allowed = filter_curriculum_sources(db, CurriculumPermissionService.allowed_sources(db, expert, role_category='teacher')) if expert else []
    declared = set(custom_ids)
    for scene_id in scene_ids:
        for group in scenes[scene_id].source_groups:
            declared.update(catalog.source_groups[group])
    rows = db.query(CurriculumSourceModel).filter(CurriculumSourceModel.id.in_(declared)).all() if declared else []
    by_id = {row.id: row for row in rows}
    if any(source_id not in by_id or by_id[source_id].source not in allowed for source_id in custom_ids):
        raise SourceForbidden('所选来源不可用或无权限')
    scope = [row.source for row in rows if row.source in allowed]
    if declared and not scope:
        raise SourceForbidden('所选场景的来源不可用或无权限')
    intents = list(dict.fromkeys(intent for scene_id in scene_ids for intent in scenes[scene_id].intents)) or ['curriculum']
    queries = rewrite_queries(goal, teaching_context, scene_ids, intents)
    pack = {'scene_ids': scene_ids, 'curriculum_evidence': [], 'teaching_cases': [],
            'environment_facts': [], 'available_resources': [], 'implementation_constraints': [],
            'missing_information': [], 'evidence_refs': [], 'queries': queries, 'sources': [], 'status': 'no_sources'}
    if not scope:
        pack['missing_information'].append('暂无可用知识依据')
        return pack
    seen = set()
    for item in queries:
        text, info = retrieve_authorized(db, workspace_id=workspace_id, run_id=run_id, user_id=user_id,
                                         expert_id=expert, configured_experts=configured, query=item['query'],
                                         source_scope=scope)
        mode = info.get('mode', '')
        if mode in ('disabled', 'permission_error', 'local_bm25_error'):
            raise RuntimeError('知识检索不可用或权限无法验证')
        for record in info.get('records', []):
            key = (record.get('source'), record.get('chunk_id'))
            if key in seen:
                continue
            seen.add(key)
            source = next((row for row in rows if row.source == key[0]), None)
            if not source:
                raise SourceForbidden('检索来源不在授权范围内')
            ref = {'evidence_id': f"{source.id}:{record['chunk_id']}", 'source_id': source.id,
                   'source': source.source, 'chunk_id': record['chunk_id'], 'source_version': source.checksum,
                   'intent': item['intent'], 'retrieval_method': mode, 'expert_id': expert,
                   'title': source.title, 'snippet': str(record.get('content', ''))[:1500]}
            pack['evidence_refs'].append(ref)
            if item['intent'] == 'curriculum':
                pack['curriculum_evidence'].append(ref['evidence_id'])
            elif item['intent'] == 'teaching_case':
                pack['teaching_cases'].append(ref['evidence_id'])
    if pack['evidence_refs']:
        pack['status'] = 'retrieved'
        pack['sources'] = [{'expert_id': expert, 'source': source} for source in sorted({item['source'] for item in pack['evidence_refs']})]
    else:
        pack['status'] = 'no_results'
        pack['missing_information'].append('未检索到可用知识依据')
    return pack

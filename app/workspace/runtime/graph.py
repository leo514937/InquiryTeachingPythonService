"""Permission-checked projections of persisted agent runs."""
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.workspace.integrations.rag import assert_sources_authorized
from app.workspace.models import Artifact, ArtifactVersion, WorkspaceEvent, WorkspaceNode, WorkspaceRun


_SAFE_ERRORS = {
    'timeout': '节点执行超时，后台工作可能仍在运行',
    'model_unavailable': '模型暂不可用',
    'model_output_invalid': '模型输出未通过能力校验，请重新生成',
    'permission_denied': '权限校验未通过',
    'validation_error': '结果或输入未通过校验',
    'execution_error': '节点执行失败',
}


def _json_value(value, default):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def assert_run_sources(db, run):
    """Deny all run details if any recorded input or result source was revoked."""
    context = _json_value(run.replan_json, {})
    if run.mode == 'replan' and (not isinstance(context, dict) or not isinstance(context.get('root'), dict) or not isinstance(context.get('targets'), list)):
        raise HTTPException(status_code=403, detail='运行来源记录不可用')
    if isinstance(context, dict):
        for item in [context.get('root'), *(context.get('targets') or [])]:
            if isinstance(item, dict):
                assert_sources_authorized(db, item.get('sources', []))
    nodes = db.query(WorkspaceNode).filter_by(run_id=run.id).all()
    for node in nodes:
        result = _json_value(node.output_json, {})
        if not isinstance(result, dict) or (node.output_json and _json_value(node.output_json, None) is None):
            raise HTTPException(status_code=403, detail='运行来源记录不可用')
        assert_sources_authorized(db, result.get('sources', []))
        refs = result.get('artifact_refs', [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get('id'), str) or not isinstance(ref.get('version'), int):
                continue
            artifact = db.query(Artifact).filter_by(workspace_id=run.workspace_id, id=ref['id']).first()
            if artifact is None:
                continue
            version = db.query(ArtifactVersion).filter_by(artifact_id=artifact.id, version=ref['version']).first()
            if version is not None:
                assert_sources_authorized(db, _json_value(version.source_json, None))


def _node_data(db, run, plan_node, row):
    node_id = plan_node['id']
    inputs = _json_value(row.inputs_json, {}) if row else {}
    output = _json_value(row.output_json, {}) if row else {}
    changes = _json_value(row.changes_json, []) if row else []
    if not isinstance(inputs, dict):
        inputs = {}
    if not isinstance(output, dict):
        output = {}
    if not isinstance(changes, list):
        changes = []
    status = row.status if row else 'unknown'
    if run.status in ('failed', 'cancelled', 'completed') and status in ('queued', 'running') and row and not row.started_at:
        status = 'unknown'
    safe_refs = []
    source_refs = []
    source_seen = set()
    def add_sources(values):
        if not isinstance(values, list):
            return
        for item in values:
            if not isinstance(item, dict):
                continue
            expert, source = item.get('expert_id'), item.get('source')
            if isinstance(expert, str) and isinstance(source, str) and (expert, source) not in source_seen:
                source_seen.add((expert, source))
                source_refs.append({'expert_id': expert, 'source': source})
    add_sources(output.get('sources', []))
    seen = set()
    refs = list(changes)
    output_refs = output.get('artifact_refs', [])
    if isinstance(output_refs, list):
        refs.extend({**ref, 'operation': 'referenced'} for ref in output_refs if isinstance(ref, dict))
    for change in refs:
        if not isinstance(change, dict):
            continue
        artifact = db.query(Artifact).filter_by(workspace_id=run.workspace_id, id=change.get('id')).first()
        if not artifact or not isinstance(change.get('version'), int):
            continue
        version = db.query(ArtifactVersion).filter_by(artifact_id=artifact.id, version=change['version']).first()
        if not version:
            continue
        assert_sources_authorized(db, _json_value(version.source_json, None))
        add_sources(_json_value(version.source_json, []))
        operation = change.get('operation')
        key = (artifact.id, version.version)
        if operation in ('created', 'updated', 'referenced') and key not in seen:
            safe_refs.append({'id': artifact.id, 'version': version.version, 'operation': operation})
            seen.add(key)
    ops = {ref['operation'] for ref in safe_refs if ref['operation'] in ('created', 'updated')}
    change_kind = ('mixed' if len(ops) > 1 else next(iter(ops), 'none')) if row and row.status == 'succeeded' and row.started_at else None
    input_parts = []
    if 'target_artifact_id' in inputs:
        input_parts.append('指定教学对象')
    if 'expert_id' in inputs or 'query' in inputs:
        input_parts.append('配置检索参数')
    if not input_parts and inputs:
        input_parts.append('已配置能力参数')
    return {
        'id': node_id, 'capability': row.capability if row else plan_node.get('capability', ''),
        'depends_on': plan_node.get('depends_on', []), 'status': status,
        'attempts': row.attempts if row else 0, 'started_at': row.started_at if row else None,
        'finished_at': row.finished_at if row else None, 'error_code': row.error_code if row else None,
        'error_message': _SAFE_ERRORS.get(row.error_code, '未记录') if row and row.error_code else None,
        'input_summary': '；'.join(input_parts) if input_parts else '未记录可展示的输入摘要',
        'output_summary': (f'关联 {len(safe_refs)} 个教学对象版本' if safe_refs else '执行结果已记录') if row and row.status == 'succeeded' else '未记录',
        'result_refs': safe_refs, 'source_refs': source_refs, 'change_kind': change_kind,
    }


def graph_projection(db, run):
    assert_run_sources(db, run)
    plan = _json_value(run.plan_json, {})
    plans = plan.get('nodes', []) if isinstance(plan, dict) else []
    if not isinstance(plans, list):
        plans = []
    plans = [node for node in plans if isinstance(node, dict) and isinstance(node.get('id'), str)]
    rows = {node.node_id: node for node in db.query(WorkspaceNode).filter_by(run_id=run.id).all()}
    ids = {node['id'] for node in plans}
    edges, incomplete = [], False
    for node in plans:
        depends = node.get('depends_on', [])
        if not isinstance(depends, list):
            incomplete = True
            continue
        saved = rows.get(node['id'])
        if saved and _json_value(saved.depends_json, None) != depends:
            incomplete = True
        for dependency in depends:
            if dependency in ids:
                edges.append({'id': f'{dependency}->{node["id"]}', 'source': dependency, 'target': node['id']})
            else:
                incomplete = True
    if set(rows) != ids:
        incomplete = True
    return {
        'id': run.id, 'mode': run.mode, 'status': run.status, 'error': '运行未完成，请查看执行详情' if run.error else None,
        'created_at': run.created_at, 'updated_at': run.updated_at,
        'nodes': [_node_data(db, run, node, rows.get(node['id'])) for node in plans],
        'edges': edges, 'incomplete': incomplete,
        'empty_reason': ('规划尚未完成' if run.status in ('queued', 'planning') else '本次运行没有可用的规划图') if not plans else None,
    }


def consistent_graph(db, run_id):
    # A matching sequence before and after the projection proves no committed
    # instrumented node transition occurred between the two reads.
    for _ in range(3):
        db.expire_all()
        before = db.execute(select(WorkspaceRun.event_sequence).where(WorkspaceRun.id == run_id)).scalar_one()
        run = db.get(WorkspaceRun, run_id)
        data = graph_projection(db, run)
        after = db.execute(select(WorkspaceRun.event_sequence).where(WorkspaceRun.id == run_id)).scalar_one()
        if before == after:
            data['event_cursor'] = after
            return data
    raise HTTPException(status_code=409, detail='运行状态正在变化，请重试')


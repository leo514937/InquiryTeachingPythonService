"""Persisted run lifecycle. No model-generated code is executed here."""
import datetime as dt
import json
import time
import threading
from contextlib import contextmanager
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from sqlalchemy import or_, update

from app.workspace.artifacts.service import _create_artifact, _id, _json, _now, _save_version
from app.workspace.models import Artifact, ArtifactDependency, ArtifactVersion, Workspace, WorkspaceActiveRun, WorkspaceEvent, WorkspaceNode, WorkspaceRun
from app.workspace.orchestrator.planner import validate_plan

_GLOBAL_NODE_SLOTS = threading.BoundedSemaphore(3)


def create_run(db, workspace_id, user_id, goal, mode, request_key, teaching_context=None):
    from app.workspace.context import TeachingContext
    context = TeachingContext.from_request(goal, teaching_context).model_dump(mode='json')
    previous = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id, request_key=request_key).first()
    if previous:
        if previous.owner_user_id != user_id or previous.goal != goal or previous.mode != mode or TeachingContext.from_request(goal, json.loads(previous.context_json or '{}')).model_dump(mode='json') != context:
            raise ValueError('idempotency key reused')
        return previous
    now = _now()
    workspace = db.query(Workspace).filter_by(id=workspace_id, owner_user_id=user_id).first()
    if workspace is None:
        raise LookupError('workspace not found')
    row = WorkspaceRun(id=_id('run'), workspace_id=workspace_id, owner_user_id=user_id,
                       request_key=request_key, goal=goal, mode=mode, input_revision=workspace.revision, context_json=_json(context),
                       status='queued', created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    db.add(WorkspaceActiveRun(workspace_id=workspace_id, run_id=row.id))
    db.flush()
    _event(db, row.id, 'queued', {})
    return row


def create_replan_run(db, workspace_id, user_id, artifact_id, expected_version, instruction, request_key):
    from app.workspace.runtime.replan import prepare_replan
    goal = f'{artifact_id}:{expected_version}:{instruction}'
    previous = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id, request_key=request_key).first()
    if previous:
        return create_run(db, workspace_id, user_id, goal, 'replan', request_key, json.loads(previous.context_json or '{}'))
    payload = prepare_replan(db, workspace_id, artifact_id)
    if payload['root']['version'] != expected_version:
        raise ValueError('version conflict')
    if not payload['targets']:
        raise ValueError('没有可自动更新的受影响对象')
    previous_run = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id, owner_user_id=user_id).filter(WorkspaceRun.mode.in_(['lesson', 'experiment'])).order_by(WorkspaceRun.created_at.desc()).first()
    prior_context = json.loads(previous_run.context_json or '{}') if previous_run else {}
    run = create_run(db, workspace_id, user_id, goal, 'replan', request_key, prior_context)
    run.replan_json = _json(payload)
    db.flush()
    return run


def _event(db, run_id, kind, data):
    # Lock the run row and allocate the cursor in the same transaction.
    sequence = db.execute(update(WorkspaceRun).where(WorkspaceRun.id == run_id)
                          .values(event_sequence=WorkspaceRun.event_sequence + 1)
                          .returning(WorkspaceRun.event_sequence),
                          execution_options={'synchronize_session': False}).scalar_one()
    db.add(WorkspaceEvent(run_id=run_id, sequence=sequence, kind=kind, data_json=_json(data), created_at=_now()))
    db.flush()


def _finish_uncommitted_nodes(db, run_id, reason):
    for node in db.query(WorkspaceNode).filter(WorkspaceNode.run_id == run_id, WorkspaceNode.status.in_(['queued', 'running'])).all():
        node.status = ('cancelled' if reason == 'cancelled' else 'skipped') if node.status == 'queued' else 'result_discarded'
        if node.status != 'result_discarded':
            node.finished_at = _now()
        _event(db, run_id, 'node_' + node.status, {'node_id': node.node_id, 'status': node.status})


def _safe_error_code(exc):
    from app.workspace.enrichment import NoEvidence, SourceForbidden
    from app.workspace.integrations.llm import ModelUnavailable
    from app.workspace.capabilities.builtin import ModelOutputInvalid
    from app.workspace.orchestrator.planner import PlanValidationError
    if isinstance(exc, NoEvidence):
        return 'no_evidence'
    if isinstance(exc, SourceForbidden):
        return 'source_forbidden'
    if isinstance(exc, PlanValidationError):
        return 'plan_invalid'
    if isinstance(exc, ModelOutputInvalid):
        return 'model_output_invalid'
    if isinstance(exc, TimeoutError):
        return 'timeout'
    if isinstance(exc, ModelUnavailable):
        return 'model_unavailable'
    if isinstance(exc, PermissionError):
        return 'permission_denied'
    if isinstance(exc, ValueError):
        return 'validation_error'
    return 'execution_error'


def cancel_run(db, run_id):
    # Serialize cancellation with a worker's lease-guarded commit before
    # inspecting nodes, so a committed success is never overwritten.
    changed = db.execute(update(WorkspaceRun).where(
        WorkspaceRun.id == run_id, WorkspaceRun.status.notin_(['completed', 'failed', 'cancelled'])
    ).values(cancel_requested=1, status='cancelled', updated_at=_now()),
        execution_options={'synchronize_session': False})
    row = db.get(WorkspaceRun, run_id)
    if not row:
        raise LookupError('run not found')
    db.refresh(row)
    if changed.rowcount:
        db.query(WorkspaceActiveRun).filter_by(workspace_id=row.workspace_id, run_id=row.id).delete(synchronize_session=False)
        _finish_uncommitted_nodes(db, row.id, 'cancelled')
        _event(db, row.id, 'cancel_requested', {})
    db.flush()
    return row


def _hold_lease(db, run_id, owner):
    now = _now()
    lease = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat()
    changed = db.execute(update(WorkspaceRun).where(
        WorkspaceRun.id == run_id, WorkspaceRun.lease_owner == owner,
        WorkspaceRun.lease_until > now, WorkspaceRun.cancel_requested == 0,
        WorkspaceRun.status.in_(['planning', 'running']),
    ).values(lease_until=lease, updated_at=now), execution_options={'synchronize_session': False})
    return changed.rowcount == 1


@contextmanager
def _node_pool():
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        yield pool
    finally:
        # A timed-out handler can finish later, but only the scheduler commits
        # node output, after checking the current lease and authorization.
        pool.shutdown(wait=False, cancel_futures=True)


def execute_run(session_factory, run_id, planner, invoke, validate_completion=None, validate_planned=None, check_access=None, retry_delays=(1, 2), review_reason=None, node_timeout=None):
    """Claim a run and execute its validated plan with persistent node results.

    The caller supplies a trusted planner and invoker. This helper does not
    construct a production invoker or expose itself as a public endpoint.
    """
    owner = _id('worker')
    failed_node_id = None
    now = _now()
    lease = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat()
    with session_factory.begin() as db:
        claimed = db.execute(update(WorkspaceRun).where(
            WorkspaceRun.id == run_id,
            WorkspaceRun.cancel_requested == 0,
            or_(WorkspaceRun.status == 'queued',
                (WorkspaceRun.status.in_(['planning', 'running']) & (WorkspaceRun.lease_until < now))),
        ).values(status='planning', lease_owner=owner, lease_until=lease, updated_at=now))
        if claimed.rowcount != 1:
            return
        row = db.get(WorkspaceRun, run_id)
        goal, saved_plan = row.goal, row.plan_json
        _event(db, run_id, 'planning', {})
    try:
        with session_factory.begin() as db:
            if not _hold_lease(db, run_id, owner):
                return
            if check_access:
                check_access(db, db.get(WorkspaceRun, run_id).owner_user_id)
        plan = validate_plan(json.loads(saved_plan)) if saved_plan and saved_plan != '{}' else validate_plan(planner(goal).model_dump())
        if validate_planned:
            validate_planned(plan)
        with session_factory.begin() as db:
            if not _hold_lease(db, run_id, owner):
                return
            row = db.get(WorkspaceRun, run_id)
            if check_access:
                check_access(db, row.owner_user_id)
            if row.cancel_requested or row.lease_owner != owner:
                row.status = 'cancelled' if row.cancel_requested else row.status
                return
            row.plan_json = plan.model_dump_json()
            row.status = 'running'
            for node in plan.nodes:
                if not db.query(WorkspaceNode).filter_by(run_id=run_id, node_id=node.id).first():
                    db.add(WorkspaceNode(run_id=run_id, node_id=node.id, capability=node.capability,
                                         depends_json=_json(node.depends_on), inputs_json=_json(node.inputs)))
            _event(db, run_id, 'running', {'nodes': len(plan.nodes)})
        pending = {node.id: node for node in plan.nodes}
        outputs = {}
        with session_factory() as db:
            for saved in db.query(WorkspaceNode).filter_by(run_id=run_id, status='succeeded').all():
                outputs[saved.node_id] = json.loads(saved.output_json)
                pending.pop(saved.node_id, None)
        active, deadlines = {}, {}
        def invoke_with_retry(node, dependencies):
            from app.workspace.integrations.llm import ModelUnavailable
            for attempt in range(len(retry_delays) + 1):
                with session_factory.begin() as db:
                    if not _hold_lease(db, run_id, owner):
                        raise RuntimeError('run no longer active')
                    row = db.get(WorkspaceRun, run_id)
                    if check_access:
                        check_access(db, row.owner_user_id)
                    saved = db.query(WorkspaceNode).filter_by(run_id=run_id, node_id=node.id).one()
                    saved.attempts += 1
                    _event(db, run_id, 'node_attempt', {'node_id': node.id, 'status': 'running', 'attempts': saved.attempts})
                try:
                    return invoke(node, dependencies)
                except ModelUnavailable as exc:
                    if not exc.retryable or attempt == len(retry_delays):
                        raise
                    with session_factory.begin() as db:
                        if not _hold_lease(db, run_id, owner):
                            raise RuntimeError('run no longer active')
                        _event(db, run_id, 'node_retry', {'node_id': node.id, 'status': 'running',
                                                          'attempts': attempt + 1, 'error_code': 'model_unavailable'})
                    time.sleep(retry_delays[attempt])
        def invoke_limited(node, dependencies):
            if not _GLOBAL_NODE_SLOTS.acquire(blocking=False):
                raise RuntimeError('capability capacity exhausted')
            try:
                return invoke_with_retry(node, dependencies)
            finally:
                _GLOBAL_NODE_SLOTS.release()
        with _node_pool() as pool:
            while pending or active:
                for node_id, ready in list(pending.items()):
                    if len(active) >= 3:
                        break
                    if not all(dep in outputs for dep in ready.depends_on):
                        continue
                    with session_factory.begin() as db:
                        if not _hold_lease(db, run_id, owner):
                            return
                        row = db.get(WorkspaceRun, run_id)
                        if check_access:
                            check_access(db, row.owner_user_id)
                        if row.cancel_requested or row.lease_owner != owner:
                            if row.cancel_requested:
                                row.status = 'cancelled'
                                _event(db, run_id, 'cancelled', {})
                            return
                        saved = db.query(WorkspaceNode).filter_by(run_id=run_id, node_id=ready.id).one()
                        saved.status = 'running'
                        saved.started_at = _now()
                        saved.finished_at = None
                        saved.error_code = None
                        _event(db, run_id, 'node_started', {'node_id': ready.id, 'status': 'running'})
                    future = pool.submit(invoke_limited, ready, {dep: outputs[dep] for dep in ready.depends_on})
                    active[future] = ready
                    deadlines[future] = time.monotonic() + (node_timeout(ready) if node_timeout else 90)
                    del pending[node_id]
                if not active:
                    raise ValueError('unresolved dependencies')
                remaining = max(0, min(deadlines.values()) - time.monotonic())
                completed, _ = wait(active, timeout=min(remaining, 1), return_when=FIRST_COMPLETED)
                expired = [future for future, deadline in deadlines.items() if future not in completed and deadline <= time.monotonic()]
                if expired:
                    failed_node_id = active[expired[0]].id
                    raise TimeoutError('capability timed out')
                if not completed:
                    with session_factory.begin() as db:
                        if not _hold_lease(db, run_id, owner):
                            return
                    continue
                for future in completed:
                    ready = active.pop(future)
                    deadlines.pop(future)
                    failed_node_id = ready.id
                    result = future.result()
                    with session_factory.begin() as db:
                        if not _hold_lease(db, run_id, owner):
                            return
                        row = db.get(WorkspaceRun, run_id)
                        if check_access:
                            check_access(db, row.owner_user_id)
                        if row.cancel_requested or row.lease_owner != owner:
                            if row.cancel_requested:
                                row.status = 'cancelled'
                                _event(db, run_id, 'cancelled', {})
                            return
                        saved = db.query(WorkspaceNode).filter_by(run_id=run_id, node_id=ready.id).one()
                        saved.status = 'succeeded'
                        saved.finished_at = _now()
                        changes = []
                        if isinstance(result, dict) and 'artifacts' in result:
                            from app.workspace.integrations.rag import assert_sources_authorized
                            sources = result.get('sources', [])
                            assert_sources_authorized(db, sources)
                            protected = db.execute(update(Workspace).where(Workspace.id == row.workspace_id, Workspace.revision == row.input_revision)
                                                   .values(revision=Workspace.revision), execution_options={'synchronize_session': False})
                            if protected.rowcount != 1:
                                raise ValueError('workspace changed while running')
                            refs = []
                            target_id = ready.inputs.get('target_artifact_id') if row.mode == 'replan' else None
                            replan_data = json.loads(row.replan_json) if row.mode == 'replan' else {}
                            targets = {target['id']: target for target in replan_data.get('targets', [])}
                            if row.mode == 'replan' and ((target_id and (target_id not in targets or len(result['artifacts']) != 1)) or (not target_id and result['artifacts'])):
                                raise ValueError('invalid replan target')
                            for artifact in result['artifacts']:
                                if target_id:
                                    target = targets[target_id]
                                    created = db.query(Artifact).filter_by(id=target_id, workspace_id=row.workspace_id).first()
                                    version = db.query(ArtifactVersion).filter_by(artifact_id=target_id, version=target['version']).first()
                                    if not created or created.version != target['version'] or created.locked or created.review_status in ('approved', 'needs_review') or created.status != 'stale' or not version or version.author_kind != 'agent' or artifact['type'] != created.type:
                                        raise ValueError('replan target changed or protected')
                                    combined = json.loads(created.source_json) + sources
                                    inherited = list({(item['expert_id'], item['source']): item for item in combined}.values())
                                    assert_sources_authorized(db, inherited)
                                    created = _save_version(db, created, target['version'], artifact['content'], sources=inherited,
                                                            author_kind='agent', run_id=run_id, increment_revision=False)
                                    created.status = 'active'
                                else:
                                    server_id = artifact.get('server_id') if ready.capability == 'quality.rules@1' else None
                                    created = _create_artifact(db, row.workspace_id, artifact['type'], artifact['content'],
                                                               sources=sources, author_kind='agent', run_id=run_id,
                                                               artifact_id=server_id)
                                refs.append({'id': created.id, 'version': created.version})
                                changes.append({'id': created.id, 'version': created.version, 'operation': 'updated' if target_id else 'created'})
                                if ready.capability == 'quality.rules@1':
                                    for field in ('goal_ids', 'activity_ids'):
                                        for upstream_id in created.content.get(field, []):
                                            upstream = db.query(Artifact).filter_by(id=upstream_id, workspace_id=row.workspace_id).first()
                                            if upstream is None:
                                                raise ValueError('invalid artifact reference')
                                            db.add(ArtifactDependency(workspace_id=row.workspace_id, upstream_id=upstream.id,
                                                                      upstream_version=upstream.version, upstream_field='',
                                                                      downstream_id=created.id, downstream_field='/' + field))
                                for dependency_id in ready.depends_on:
                                    for upstream in outputs[dependency_id].get('artifact_refs', []):
                                        if upstream['id'] == created.id:
                                            continue
                                        db.add(ArtifactDependency(workspace_id=row.workspace_id, upstream_id=upstream['id'],
                                                                  upstream_version=upstream['version'], upstream_field='',
                                                                  downstream_id=created.id, downstream_field=''))
                            if not refs:
                                inherited_refs = [ref for dependency_id in ready.depends_on for ref in outputs[dependency_id].get('artifact_refs', [])]
                                refs = list({(ref['id'], ref['version']): ref for ref in inherited_refs}.values())
                            result['artifact_refs'] = refs
                        saved.output_json = _json(result)
                        saved.changes_json = _json(changes)
                        _event(db, run_id, 'node_succeeded', {'node_id': ready.id, 'status': 'succeeded', 'capability': ready.capability})
                    outputs[ready.id] = result
                    failed_node_id = None
        completion_status = validate_completion(outputs) if validate_completion else 'completed'
        if completion_status not in ('completed', 'waiting_review'):
            raise ValueError('invalid completion state')
        with session_factory.begin() as db:
            if not _hold_lease(db, run_id, owner):
                return
            row = db.get(WorkspaceRun, run_id)
            if check_access:
                check_access(db, row.owner_user_id)
            if row.lease_owner == owner:
                protected = db.execute(update(Workspace).where(Workspace.id == row.workspace_id, Workspace.revision == row.input_revision)
                                       .values(revision=Workspace.revision), execution_options={'synchronize_session': False})
                if protected.rowcount != 1:
                    raise ValueError('workspace changed during final validation')
                from app.workspace.integrations.rag import assert_sources_authorized
                for result in outputs.values():
                    if isinstance(result, dict):
                        assert_sources_authorized(db, result.get('sources', []))
                row.status = 'cancelled' if row.cancel_requested else completion_status
                if row.status == 'waiting_review':
                    row.error = (review_reason() if review_reason else '') or '自动检查存在不确定性，请教师审核教学内容与安全约束。'
                else:
                    db.query(WorkspaceActiveRun).filter_by(workspace_id=row.workspace_id, run_id=row.id).delete(synchronize_session=False)
                row.updated_at = _now()
                _event(db, run_id, row.status, {})
    except Exception as exc:
        with session_factory.begin() as db:
            if _hold_lease(db, run_id, owner):
                row = db.get(WorkspaceRun, run_id)
                row.status = 'cancelled' if row.cancel_requested else 'failed'
                row.error = ('' if row.cancel_requested else
                             '暂无可用知识依据，请确认是否使用通用教学建议继续' if _safe_error_code(exc) == 'no_evidence' else
                             '所选知识来源不可用或无权限' if _safe_error_code(exc) == 'source_forbidden' else
                             '模型服务未配置或暂不可用，请检查配置后重试' if _safe_error_code(exc) == 'model_unavailable' else
                             '模型返回的教学内容未通过校验，请重新生成' if _safe_error_code(exc) == 'model_output_invalid' else
                             '模型返回的编排计划未通过校验，请调整需求后重试' if _safe_error_code(exc) == 'plan_invalid' else
                             '执行失败，请检查配置后重试')
                row.updated_at = _now()
                if failed_node_id:
                    node = db.query(WorkspaceNode).filter_by(run_id=run_id, node_id=failed_node_id).first()
                    if node and node.status == 'running':
                        node.status, node.finished_at, node.error_code = 'failed', (None if isinstance(exc, TimeoutError) else _now()), _safe_error_code(exc)
                        _event(db, run_id, 'node_failed', {'node_id': node.node_id, 'status': 'failed', 'error_code': node.error_code})
                _finish_uncommitted_nodes(db, run_id, row.status)
                db.query(WorkspaceActiveRun).filter_by(workspace_id=row.workspace_id, run_id=row.id).delete(synchronize_session=False)
                _event(db, run_id, row.status, {})


def execute_builtin_run(session_factory, run_id, model, authorize=None):
    from app.workspace.capabilities.builtin import build_registry
    from app.workspace.integrations.rag import assert_sources_authorized
    from app.workspace.integrations.rag import get_allowed_experts
    from app.workspace.orchestrator.planner import plan_goal
    if authorize is None:
        def authorize(db, user_id):
            from app.db.models import UserModel
            from app.services.session_access_service import resolve_workspace_role
            user = db.get(UserModel, user_id)
            if user is None:
                raise PermissionError('user unavailable')
            resolve_workspace_role(db, user, 'teacher')
    with session_factory() as db:
        run = db.get(WorkspaceRun, run_id)
        if run is None:
            return
        context = {'workspace_id': run.workspace_id, 'run_id': run.id, 'user_id': run.owner_user_id}
        goal, mode = run.goal, run.mode
        from app.workspace.context import TeachingContext
        teaching_context = TeachingContext.from_request(goal, json.loads(run.context_json or '{}')).model_dump(mode='json')
        allowed_experts = get_allowed_experts(db)
        replan_data = json.loads(run.replan_json) if mode == 'replan' else None
    registry = build_registry(model, session_factory)
    evaluation_covered = False
    evaluation_reasons = []
    def invoke(node, dependencies):
        if replan_data:
            sources = [source for item in [replan_data['root'], *replan_data['targets']] for source in item['sources']]
            dependencies = {**dependencies, '_workspace_context': {'summary': json.dumps(replan_data, ensure_ascii=False), 'sources': sources}}
        with session_factory() as db:
            authorize(db, context['user_id'])
            for value in dependencies.values():
                assert_sources_authorized(db, value.get('sources', []))
        result = registry.invoke(node.capability, context, {'goal': goal, 'parameters': node.inputs, 'dependencies': dependencies, 'teaching_context': teaching_context})
        result['capability'] = node.capability
        return result
    def validate_completion(outputs):
        from app.workspace.orchestrator.evaluator import evaluate_completion
        status, reasons = evaluate_completion(mode, outputs, evaluation_covered)
        evaluation_reasons[:] = reasons
        if status == 'failed':
            raise ValueError('incomplete teaching design')
        return status
    def validate_planned(plan):
        nonlocal evaluation_covered
        artifact_caps = {'knowledge.map@1', 'goals.compose@1', 'inquiry.design@1', 'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1', 'assessment.design@1', 'report.narrative@1'}
        producers = {n.id for n in plan.nodes if n.capability in {'goals.compose@1', 'inquiry.design@1', 'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1', 'assessment.design@1'}}
        by_id = {n.id: n for n in plan.nodes}
        def ancestors(node):
            seen, queue = set(), list(node.depends_on)
            while queue:
                current = queue.pop()
                if current not in seen:
                    seen.add(current)
                    queue.extend(by_id[current].depends_on)
            return seen
        evaluation_covered = any(producers.issubset(ancestors(n)) for n in plan.nodes if n.capability == 'quality.evaluate@1')
        if teaching_context.get('studio_mode'):
            evaluation_covered = any(n.capability == 'quality.rules@1' and 'bundle' in n.depends_on for n in plan.nodes)
        if replan_data:
            target_ids = [item['id'] for item in replan_data['targets']]
            target_nodes = {node.inputs.get('target_artifact_id'): node for node in plan.nodes if node.capability in artifact_caps}
            selected = [node.inputs.get('target_artifact_id') for node in plan.nodes if node.capability in artifact_caps]
            if sorted(selected, key=str) != sorted(target_ids):
                raise ValueError('invalid replan target set')
            for edge in replan_data.get('edges', []):
                if target_nodes[edge['upstream_id']].id not in ancestors(target_nodes[edge['downstream_id']]):
                    raise ValueError('replan omitted artifact dependency')
    def planner(text):
        if teaching_context.get('studio_mode') and mode == 'lesson':
            from app.workspace.orchestrator.planner import studio_plan
            return studio_plan(text)
        if replan_data:
            with session_factory() as db:
                authorize(db, context['user_id'])
                for item in [replan_data['root'], *replan_data['targets']]:
                    assert_sources_authorized(db, item['sources'])
        return plan_goal(model, text, mode=mode, allowed_experts=allowed_experts, replan_context=replan_data,
                         validate_context=validate_planned, teaching_context=teaching_context)
    execute_run(session_factory, run_id, planner, invoke, validate_completion, validate_planned, authorize,
                review_reason=lambda: '；'.join(evaluation_reasons) + '，请教师审核。' if evaluation_reasons else '',
                node_timeout=lambda node: registry.get(node.capability).timeout_seconds)

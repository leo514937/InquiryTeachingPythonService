import pytest
import httpx
from types import SimpleNamespace

from app.workspace.orchestrator.planner import validate_plan, plan_goal
from app.workspace.integrations.llm import StrictLLM, ModelUnavailable


def node(name, capability, dependencies=()):
    return {'id': name, 'capability': capability, 'depends_on': list(dependencies), 'inputs': {}}


def test_valid_plans_can_have_different_capability_graphs():
    full = {'version': 1, 'goal': '完整教学设计', 'nodes': [node('r', 'requirements.analyze@1'), node('g', 'goals.compose@1', ['r']), node('a', 'assessment.design@1', ['g'])]}
    experiment = {'version': 1, 'goal': '独立实验', 'nodes': [node('r', 'requirements.analyze@1'), node('x', 'activity.design@1', ['r']), node('c', 'component.bind@1', ['x'])]}
    assert validate_plan(full).nodes[-1].capability == 'assessment.design@1'
    assert validate_plan(experiment).nodes[-1].capability == 'component.bind@1'


@pytest.mark.parametrize('nodes', [
    [node('a', 'unknown@1')],
    [node('a', 'requirements.analyze@1', ['missing'])],
    [node('a', 'requirements.analyze@1', ['b']), node('b', 'goals.compose@1', ['a'])],
    [node('a', 'requirements.analyze@1'), node('a', 'goals.compose@1')],
])
def test_invalid_plan_is_rejected(nodes):
    with pytest.raises(ValueError):
        validate_plan({'version': 1, 'goal': '测试', 'nodes': nodes})


def test_strict_llm_never_substitutes_mock_output():
    settings = SimpleNamespace(llm_api_key='key', llm_api_base='https://example.test/v1', llm_model='model')
    transport = httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ModelUnavailable):
            StrictLLM(settings, client).complete('system', 'user')


def test_strict_llm_uses_real_response_content():
    settings = SimpleNamespace(llm_api_key='key', llm_api_base='https://example.test/v1', llm_model='model')
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': '{"ok":true}'}}]}, request=request))
    with httpx.Client(transport=transport) as client:
        assert StrictLLM(settings, client).complete('system', 'user') == '{"ok":true}'


def test_model_plan_is_validated_before_use():
    class Model:
        def complete(self, system, message):
            assert 'activity.design@1' in system
            assert '反射实验' in message
            return '{"version":1,"goal":"反射实验","nodes":[{"id":"a","capability":"activity.design@1","depends_on":[],"inputs":{}}]}'
    assert plan_goal(Model(), '反射实验').nodes[0].capability == 'activity.design@1'


def test_model_plan_does_not_execute_unknown_capability():
    class Model:
        def complete(self, system, message):
            return '{"version":1,"goal":"测试","nodes":[{"id":"a","capability":"shell@1","depends_on":[],"inputs":{}}]}'
    with pytest.raises(ValueError):
        plan_goal(Model(), '测试')


def test_lesson_planner_repairs_missing_curriculum_retrieval():
    import json
    class Model:
        calls = 0
        def complete(self, system, message):
            self.calls += 1
            nodes = [node('goal', 'goals.compose@1'), node('question', 'inquiry.design@1'), node('activity', 'activity.design@1', ['goal']), node('assessment', 'assessment.design@1', ['goal'])]
            if self.calls == 2:
                nodes.insert(0, node('rag', 'knowledge.retrieve@1'))
                nodes[1]['depends_on'] = ['rag']
            return json.dumps({'version': 1, 'goal': '教学设计', 'nodes': nodes}, ensure_ascii=False)
    model = Model()
    plan = plan_goal(model, '教学设计', mode='lesson', allowed_experts=['physics_teacher_agent'])
    assert model.calls == 2 and plan.nodes[0].capability == 'knowledge.retrieve@1'


def test_planner_repairs_contextual_validation_error():
    import json
    class Model:
        calls = 0
        def complete(self, system, message):
            self.calls += 1
            if self.calls == 2:
                assert 'replan omitted artifact dependency' in message
            nodes = [node('first', 'activity.design@1'), node('second', 'assessment.design@1', ['first'] if self.calls == 2 else [])]
            return json.dumps({'version': 1, 'goal': '调整', 'nodes': nodes})
    def validate_context(plan):
        if 'first' not in plan.nodes[1].depends_on:
            raise ValueError('replan omitted artifact dependency')
    model = Model()
    result = plan_goal(model, '调整', mode='replan', validate_context=validate_context)
    assert model.calls == 2 and result.nodes[1].depends_on == ['first']


def test_workspace_change_during_final_validation_prevents_completion(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun, Workspace
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "final-revision.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        workspace_id = workspace.id
        run_id = create_run(db, workspace_id, 'teacher', '反射', 'experiment', 'revision').id
    plan = validate_plan({'version': 1, 'goal': '反射', 'nodes': [node('a', 'requirements.analyze@1')]})
    def validate(outputs):
        with factory.begin() as db:
            db.get(Workspace, workspace_id).revision += 1
        return 'completed'
    execute_run(factory, run_id, lambda goal: plan, lambda *_: {'summary': 'ok'}, validate)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status != 'completed'
    engine.dispose()


def test_source_revocation_during_final_validation_prevents_completion(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    from app.workspace.integrations import rag
    engine = create_engine(f'sqlite:///{(tmp_path / "final-revoke.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '反射', 'experiment', 'revoke').id
    revoked = False
    def check_sources(db, sources):
        if revoked and sources:
            raise PermissionError('source revoked')
    monkeypatch.setattr(rag, 'assert_sources_authorized', check_sources)
    plan = validate_plan({'version': 1, 'goal': '反射', 'nodes': [node('a', 'knowledge.retrieve@1')]})
    def validate(outputs):
        nonlocal revoked
        revoked = True
        return 'completed'
    execute_run(factory, run_id, lambda goal: plan, lambda *_: {'sources': [{'expert_id': 'e', 'source': 's'}]}, validate)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status != 'completed'
    engine.dispose()


def test_non_llm_capability_timeout_fails_without_late_commit(tmp_path):
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun, WorkspaceNode
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "timeout.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '反射', 'experiment', 'timeout').id
    release = threading.Event()
    plan = validate_plan({'version': 1, 'goal': '反射', 'nodes': [node('slow', 'knowledge.retrieve@1')]})
    def invoke(node_value, dependencies):
        release.wait(5)
        return {'summary': 'too late'}
    try:
        execute_run(factory, run_id, lambda goal: plan, invoke, node_timeout=lambda _: 0.05)
        with factory() as db:
            assert db.get(WorkspaceRun, run_id).status == 'failed'
            assert db.query(WorkspaceNode).filter_by(run_id=run_id, node_id='slow').one().status != 'succeeded'
    finally:
        release.set()
        engine.dispose()


def test_global_node_limit_does_not_start_more_handlers(tmp_path, monkeypatch):
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime import runs
    engine = create_engine(f'sqlite:///{(tmp_path / "limit.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = runs.create_run(db, workspace.id, 'teacher', '反射', 'experiment', 'limit').id
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(runs, '_GLOBAL_NODE_SLOTS', slots)
    plan = validate_plan({'version': 1, 'goal': '反射', 'nodes': [node('a', 'knowledge.retrieve@1')]})
    try:
        runs.execute_run(factory, run_id, lambda goal: plan, lambda *_: pytest.fail('handler exceeded global limit'))
        with factory() as db:
            assert db.get(WorkspaceRun, run_id).status == 'failed'
    finally:
        slots.release()
        engine.dispose()


def test_persistent_run_is_idempotent_and_executes_validated_nodes(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceNode, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        workspace_id = workspace.id
        run = create_run(db, workspace_id, 'teacher', '反射实验', 'experiment', 'same-key')
        run_id = run.id
        assert create_run(db, workspace_id, 'teacher', '反射实验', 'experiment', 'same-key').id == run_id
        with pytest.raises(ValueError):
            create_run(db, workspace_id, 'teacher', '不同需求', 'experiment', 'same-key')
    plan = validate_plan({'version': 1, 'goal': '反射实验', 'nodes': [
        node('a', 'requirements.analyze@1'), node('b', 'activity.design@1', ['a']),
    ]})
    calls = []
    def invoke(node_value, dependencies):
        calls.append(node_value.id)
        return {'value': node_value.id}
    execute_run(factory, run_id, lambda goal: plan, invoke)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        assert [n.status for n in db.query(WorkspaceNode).filter_by(run_id=run_id).order_by(WorkspaceNode.id)] == ['succeeded', 'succeeded']
    assert calls == ['a', 'b']
    engine.dispose()


def test_cancelled_run_never_invokes_planner(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, cancel_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run = create_run(db, workspace.id, 'teacher', '需求', 'lesson', 'key')
        run_id = run.id
        cancel_run(db, run_id)
    execute_run(factory, run_id, lambda goal: pytest.fail('planner called'), lambda *args: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'cancelled'
    engine.dispose()


def test_builtin_run_creates_structured_artifacts_from_model(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import Artifact, WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '反射实验', 'experiment', 'key').id
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '反射实验', 'nodes': [node('experiment', 'activity.design@1'), node('quality', 'quality.evaluate@1', ['experiment'])]}, ensure_ascii=False)
            if 'quality.evaluate@1' in system:
                return '{"summary":"通过","artifacts":[],"warnings":[]}'
            return json.dumps({'summary': '实验', 'artifacts': [{'type': 'Experiment', 'content': {'title': '反射', 'description': '观察光线', 'materials': ['镜子'], 'safety_measures': ['成人监督'], 'component_type': 'light_reflection_v1'}}], 'warnings': []}, ensure_ascii=False)
    execute_builtin_run(factory, run_id, Model(), authorize=lambda db, user_id: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        assert db.query(Artifact).filter_by(type='Experiment').one().content['title'] == '反射'
    engine.dispose()


def test_builtin_run_does_not_claim_success_without_required_artifact(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '反射实验', 'experiment', 'key').id
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '反射实验', 'nodes': [node('analysis', 'requirements.analyze@1')]}, ensure_ascii=False)
            return '{"summary":"分析","artifacts":[],"warnings":[]}'
    execute_builtin_run(factory, run_id, Model(), authorize=lambda db, user_id: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'failed'
    engine.dispose()


def test_worker_processes_queued_run_with_independent_sessions(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run
    from app.workspace.runtime.worker import WorkspaceWorker
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '反射实验', 'experiment', 'key').id
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '反射实验', 'nodes': [node('experiment', 'activity.design@1'), node('quality', 'quality.evaluate@1', ['experiment'])]}, ensure_ascii=False)
            if 'quality.evaluate@1' in system:
                return '{"summary":"通过","artifacts":[],"warnings":[]}'
            return '{"summary":"实验","artifacts":[{"type":"Experiment","content":{"title":"反射","description":"观察","materials":["镜子"],"safety_measures":["监督"]}}],"warnings":[]}'
    assert WorkspaceWorker(factory, Model(), authorize=lambda db, user_id: None).process_next() is True
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
    assert WorkspaceWorker(factory, Model(), authorize=lambda db, user_id: None).process_next() is False
    engine.dispose()


def test_builtin_run_requires_review_when_evaluation_missing(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "runtime.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '实验', 'experiment', 'key').id
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '实验', 'nodes': [node('a', 'activity.design@1')]}, ensure_ascii=False)
            return '{"summary":"实验","artifacts":[{"type":"Experiment","content":{"title":"反射"}}],"warnings":[]}'
    execute_builtin_run(factory, run_id, Model(), authorize=lambda db, user_id: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'waiting_review'
        assert '审核' in db.get(WorkspaceRun, run_id).error
    engine.dispose()


def test_persisted_scheduler_runs_ready_nodes_in_parallel(tmp_path):
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "parallel.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '需求', 'lesson', 'key').id
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'requirements.analyze@1'), node('b', 'knowledge.map@1'), node('c', 'goals.compose@1', ['a', 'b'])]})
    barrier = threading.Barrier(2, timeout=2)
    def invoke(node_value, dependencies):
        if node_value.id in ('a', 'b'):
            barrier.wait()
        else:
            assert set(dependencies) == {'a', 'b'}
        return {'value': node_value.id}
    execute_run(factory, run_id, lambda goal: plan, invoke)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
    engine.dispose()


def test_cancel_while_node_runs_prevents_artifact_commit(tmp_path):
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import Artifact, WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, cancel_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "cancel.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '需求', 'experiment', 'key').id
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'activity.design@1')]})
    started, release = threading.Event(), threading.Event()
    def invoke(node_value, dependencies):
        started.set()
        assert release.wait(3)
        return {'artifacts': [{'type': 'Experiment', 'content': {'title': '反射'}}], 'sources': []}
    thread = threading.Thread(target=execute_run, args=(factory, run_id, lambda goal: plan, invoke))
    thread.start()
    assert started.wait(3)
    with factory.begin() as db:
        cancel_run(db, run_id)
    release.set()
    thread.join(3)
    assert not thread.is_alive()
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'cancelled'
        assert db.query(Artifact).count() == 0
    engine.dispose()


def test_expired_lease_resumes_without_repeating_completed_node(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceNode, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "resume.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'requirements.analyze@1'), node('b', 'activity.design@1', ['a'])]})
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run = create_run(db, workspace.id, 'teacher', '需求', 'experiment', 'key')
        run.status, run.lease_until, run.lease_owner, run.plan_json = 'running', '2000-01-01', 'old', plan.model_dump_json()
        run_id = run.id
        db.add(WorkspaceNode(run_id=run_id, node_id='a', capability='requirements.analyze@1', depends_json='[]', inputs_json='{}', output_json=json.dumps({'result': 'saved'}), status='succeeded'))
    calls = []
    def invoke(node_value, dependencies):
        calls.append(node_value.id)
        assert dependencies['a'] == {'result': 'saved'}
        return {'result': 'new'}
    execute_run(factory, run_id, lambda goal: pytest.fail('replanned'), invoke)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
    assert calls == ['b']
    engine.dispose()


def test_generated_artifacts_record_dependencies_between_nodes(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import Artifact, ArtifactDependency, WorkspaceBase
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "dependencies.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run_id = create_run(db, workspace.id, 'teacher', '需求', 'lesson', 'key').id
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'goals.compose@1'), node('b', 'activity.design@1', ['a'])]})
    def invoke(node_value, dependencies):
        kind = 'LearningGoal' if node_value.id == 'a' else 'Experiment'
        return {'artifacts': [{'type': kind, 'content': {'title': node_value.id}}], 'sources': []}
    execute_run(factory, run_id, lambda goal: plan, invoke)
    with factory() as db:
        goal = db.query(Artifact).filter_by(type='LearningGoal').one()
        experiment = db.query(Artifact).filter_by(type='Experiment').one()
        dependency = db.query(ArtifactDependency).one()
        assert dependency.upstream_id == goal.id and dependency.downstream_id == experiment.id
    engine.dispose()


def test_dependencies_pass_through_nodes_without_artifacts(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import Artifact, ArtifactDependency, WorkspaceBase
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "passthrough.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 't', '反射')
        run_id = create_run(db, workspace.id, 't', '需求', 'lesson', 'key').id
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'goals.compose@1'), node('q', 'quality.evaluate@1', ['a']), node('b', 'activity.design@1', ['q'])]})
    def invoke(n, deps):
        kind = {'a': 'LearningGoal', 'b': 'Experiment'}.get(n.id)
        return {'artifacts': [{'type': kind, 'content': {'title': n.id}}] if kind else [], 'sources': []}
    execute_run(factory, run_id, lambda goal: plan, invoke)
    with factory() as db:
        goal = db.query(Artifact).filter_by(type='LearningGoal').one()
        experiment = db.query(Artifact).filter_by(type='Experiment').one()
        assert db.query(ArtifactDependency).filter_by(upstream_id=goal.id, downstream_id=experiment.id).count() == 1
    engine.dispose()


def test_local_replan_updates_only_eligible_target(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import Artifact, ArtifactDependency, WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace, create_experiment, _create_artifact, update_artifact
    from app.workspace.runtime.runs import create_replan_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "replan.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        source = create_experiment(db, workspace.id)
        activity = _create_artifact(db, workspace.id, 'InquiryActivity', {'title': '原活动'}, author_kind='agent')
        other = _create_artifact(db, workspace.id, 'Assessment', {'title': '原评价'}, author_kind='agent')
        db.add(ArtifactDependency(workspace_id=workspace.id, upstream_id=source.id, upstream_version=1, upstream_field='/materials', downstream_id=activity.id, downstream_field=''))
        db.flush()
        update_artifact(db, workspace.id, source.id, 1, {**source.content, 'materials': ['手电筒']})
        run = create_replan_run(db, workspace.id, 'teacher', source.id, 2, '调整活动', 'key')
        run_id, activity_id, other_id = run.id, activity.id, other.id
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                target = node('change', 'activity.design@1')
                target['inputs'] = {'target_artifact_id': activity_id}
                return json.dumps({'version': 1, 'goal': '调整活动', 'nodes': [target, node('quality', 'quality.evaluate@1', ['change'])]}, ensure_ascii=False)
            if 'quality.evaluate@1' in system:
                return '{"summary":"通过","artifacts":[],"warnings":[]}'
            return '{"summary":"更新","artifacts":[{"type":"InquiryActivity","content":{"title":"手电筒活动","description":"观察"}}],"warnings":[]}'
    execute_builtin_run(factory, run_id, Model(), authorize=lambda db, user_id: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        assert db.get(Artifact, activity_id).content['title'] == '手电筒活动'
        assert db.get(Artifact, activity_id).version == 2
        assert db.get(Artifact, other_id).version == 1
        from app.workspace.runtime.graph import graph_projection
        graph = graph_projection(db, db.get(WorkspaceRun, run_id))
        nodes = {node['id']: node for node in graph['nodes']}
        assert nodes['change']['change_kind'] == 'updated'
        assert nodes['change']['result_refs'] == [{'id': activity_id, 'version': 2, 'operation': 'updated'}]
        assert nodes['quality']['change_kind'] == 'none'
    engine.dispose()


def test_replan_does_not_cross_teacher_review_barrier(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import ArtifactDependency, WorkspaceBase
    from app.workspace.artifacts.service import create_workspace, create_experiment, _create_artifact, update_artifact
    from app.workspace.runtime.replan import prepare_replan
    engine = create_engine(f'sqlite:///{(tmp_path / "review-barrier.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        root = create_experiment(db, workspace.id)
        reviewed = _create_artifact(db, workspace.id, 'InquiryActivity', {'title': '教师活动'}, author_kind='teacher')
        downstream = _create_artifact(db, workspace.id, 'Assessment', {'title': '评价'}, author_kind='agent')
        db.add_all([ArtifactDependency(workspace_id=workspace.id, upstream_id=root.id, upstream_version=1, upstream_field='/materials', downstream_id=reviewed.id, downstream_field=''), ArtifactDependency(workspace_id=workspace.id, upstream_id=reviewed.id, upstream_version=1, upstream_field='', downstream_id=downstream.id, downstream_field='')])
        db.flush()
        update_artifact(db, workspace.id, root.id, 1, {**root.content, 'materials': ['手电筒']})
        assert downstream.review_status == 'needs_review'
        result = prepare_replan(db, workspace.id, root.id)
        assert result['targets'] == []
        assert set(result['requires_review']) == {reviewed.id, downstream.id}
        assert downstream.review_status == 'needs_review'
    engine.dispose()


def test_replan_rejects_plan_that_breaks_existing_target_dependencies(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import ArtifactDependency, WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace, create_experiment, _create_artifact, update_artifact
    from app.workspace.runtime.runs import create_replan_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "bad-replan.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 't', '反射')
        root = create_experiment(db, workspace.id)
        first = _create_artifact(db, workspace.id, 'InquiryActivity', {'title': '活动'}, author_kind='agent')
        second = _create_artifact(db, workspace.id, 'Assessment', {'title': '评价'}, author_kind='agent')
        db.add_all([ArtifactDependency(workspace_id=workspace.id, upstream_id=root.id, upstream_version=1, upstream_field='/materials', downstream_id=first.id, downstream_field=''), ArtifactDependency(workspace_id=workspace.id, upstream_id=first.id, upstream_version=1, upstream_field='', downstream_id=second.id, downstream_field='')])
        db.flush()
        update_artifact(db, workspace.id, root.id, 1, {**root.content, 'materials': ['手电筒']})
        run = create_replan_run(db, workspace.id, 't', root.id, 2, '调整', 'key')
        run_id, first_id, second_id = run.id, first.id, second.id
    class Model:
        calls = 0
        def complete(self, system, message):
            self.calls += 1
            a, b = node('a', 'activity.design@1'), node('b', 'assessment.design@1')
            a['inputs'], b['inputs'] = {'target_artifact_id': first_id}, {'target_artifact_id': second_id}
            return json.dumps({'version': 1, 'goal': '调整', 'nodes': [a, b]}, ensure_ascii=False)
    model = Model()
    execute_builtin_run(factory, run_id, model, authorize=lambda db, user_id: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'failed'
    assert model.calls == 2
    engine.dispose()


def test_expired_or_replaced_lease_cannot_authorize_node_commit(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, _hold_lease
    engine = create_engine(f'sqlite:///{(tmp_path / "lease.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run = create_run(db, workspace.id, 'teacher', '需求', 'lesson', 'key')
        run.status, run.lease_owner, run.lease_until = 'running', 'old', '2000-01-01'
        run_id = run.id
    with factory.begin() as db:
        assert _hold_lease(db, run_id, 'old') is False
    with factory.begin() as db:
        row = db.get(__import__('app.workspace.models', fromlist=['WorkspaceRun']).WorkspaceRun, run_id)
        row.lease_owner, row.lease_until = 'new', '9999-01-01'
    with factory.begin() as db:
        assert _hold_lease(db, run_id, 'old') is False
        assert _hold_lease(db, run_id, 'new') is True
    engine.dispose()


def test_teacher_role_revoked_before_execution_stops_before_model(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import UserModel, UserWorkspaceRoleModel
    from app.workspace.models import WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "roles.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    UserModel.__table__.create(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(UserModel(id='t', username='teacher', password_hash='x', user_role='parent', created_at='now'))
        db.add(UserWorkspaceRoleModel(user_id='t', role_category='parent', created_at='now'))
        workspace = create_workspace(db, 't', '反射')
        run_id = create_run(db, workspace.id, 't', '需求', 'experiment', 'key').id
    class Model:
        calls = 0
        def complete(self, system, message):
            self.calls += 1
            return json.dumps({'version': 1, 'goal': '需求', 'nodes': [node('a', 'activity.design@1')]})
    model = Model()
    execute_builtin_run(factory, run_id, model)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'failed'
    assert model.calls == 0
    engine.dispose()


def test_teacher_role_revoked_during_model_call_blocks_commit(tmp_path):
    import json
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import UserModel, UserWorkspaceRoleModel
    from app.workspace.models import Artifact, WorkspaceBase, WorkspaceRun
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "roles-live.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    UserModel.__table__.create(engine); UserWorkspaceRoleModel.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(UserModel(id='t', username='teacher', password_hash='x', user_role='parent', created_at='now'))
        db.add_all([UserWorkspaceRoleModel(user_id='t', role_category=role, created_at='now') for role in ('teacher', 'parent')])
        workspace = create_workspace(db, 't', '反射')
        run_id = create_run(db, workspace.id, 't', '需求', 'experiment', 'key').id
    started, release = threading.Event(), threading.Event()
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '需求', 'nodes': [node('a', 'activity.design@1')]})
            started.set(); assert release.wait(3)
            return '{"summary":"x","artifacts":[{"type":"Experiment","content":{"title":"实验"}}],"warnings":[]}'
    thread = threading.Thread(target=execute_builtin_run, args=(factory, run_id, Model()))
    thread.start(); assert started.wait(5)
    with factory.begin() as db:
        db.query(UserWorkspaceRoleModel).filter_by(user_id='t', role_category='teacher').delete()
    release.set(); thread.join(5)
    assert not thread.is_alive()
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'failed'
        assert db.query(Artifact).count() == 0
    engine.dispose()


def test_one_active_run_per_workspace_and_teacher_creates_change_revision(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase
    from app.workspace.artifacts.service import create_workspace, create_experiment
    from app.workspace.runtime.runs import create_run, cancel_run
    engine = create_engine(f'sqlite:///{(tmp_path / "active.db").as_posix()}')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 't', '反射')
        workspace_id = workspace.id
        create_experiment(db, workspace_id)
        db.refresh(workspace)
        assert workspace.revision == 1
        run = create_run(db, workspace_id, 't', '需求', 'lesson', 'one')
        run_id = run.id
    with factory() as db:
        with pytest.raises(IntegrityError):
            create_run(db, workspace_id, 't', '需求二', 'lesson', 'two')
        db.rollback()
    with factory.begin() as db:
        cancel_run(db, run_id)
    with factory.begin() as db:
        assert create_run(db, workspace_id, 't', '需求二', 'lesson', 'two').status == 'queued'
    engine.dispose()


def test_transient_node_failure_retries_at_most_twice(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase, WorkspaceRun, WorkspaceNode
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_run
    engine = create_engine(f'sqlite:///{(tmp_path / "retry.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        workspace = create_workspace(db, 't', '反射')
        run_id = create_run(db, workspace.id, 't', '需求', 'experiment', 'key').id
    plan = validate_plan({'version': 1, 'goal': '需求', 'nodes': [node('a', 'activity.design@1')]})
    calls = []
    def invoke(node_value, dependencies):
        calls.append(1)
        if len(calls) < 3:
            raise ModelUnavailable('temporary', retryable=True)
        return {'result': 'ok'}
    execute_run(factory, run_id, lambda goal: plan, invoke, retry_delays=(0, 0))
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        assert db.query(WorkspaceNode).filter_by(run_id=run_id).one().attempts == 3
        from app.workspace.models import WorkspaceEvent
        assert db.query(WorkspaceEvent).filter_by(run_id=run_id, kind='node_retry').count() == 2
    assert len(calls) == 3
    engine.dispose()

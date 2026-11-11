import threading
import time

import pytest
from pydantic import BaseModel

from app.workspace.capabilities.registry import Capability, CapabilityRegistry
from app.workspace.runtime.scheduler import execute_dag
from app.workspace.orchestrator.planner import validate_plan


class Payload(BaseModel):
    value: int


def test_registry_validates_inputs_and_outputs():
    registry = CapabilityRegistry()
    registry.register(Capability('requirements.analyze@1', Payload, Payload, lambda ctx, data: {'value': data.value + 1}))
    assert registry.invoke('requirements.analyze@1', {}, {'value': 1}) == {'value': 2}
    with pytest.raises(ValueError):
        registry.invoke('unknown@1', {}, {'value': 1})
    with pytest.raises(ValueError):
        registry.invoke('requirements.analyze@1', {}, {'value': 'not a number'})


def test_scheduler_executes_independent_nodes_concurrently_and_waits_for_dependencies():
    barrier = threading.Barrier(2, timeout=2)
    seen = []
    def invoke(node, outputs):
        if node.id in ('a', 'b'):
            barrier.wait()
            time.sleep(0.02)
        else:
            assert set(outputs) == {'a', 'b'}
        seen.append(node.id)
        return {'id': node.id}
    plan = validate_plan({'version': 1, 'goal': 'test', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {}},
        {'id': 'b', 'capability': 'knowledge.map@1', 'depends_on': [], 'inputs': {}},
        {'id': 'c', 'capability': 'goals.compose@1', 'depends_on': ['a', 'b'], 'inputs': {}},
    ]})
    result = execute_dag(plan, invoke, max_workers=3)
    assert set(result) == {'a', 'b', 'c'}
    assert seen[-1] == 'c'


def test_scheduler_never_runs_dependents_of_failure():
    calls = []
    plan = validate_plan({'version': 1, 'goal': 'test', 'nodes': [
        {'id': 'a', 'capability': 'requirements.analyze@1', 'depends_on': [], 'inputs': {}},
        {'id': 'b', 'capability': 'goals.compose@1', 'depends_on': ['a'], 'inputs': {}},
    ]})
    def invoke(node, outputs):
        calls.append(node.id)
        raise RuntimeError('failed')
    with pytest.raises(RuntimeError):
        execute_dag(plan, invoke)
    assert calls == ['a']


def test_builtin_experiment_capability_validates_structured_artifacts():
    from app.workspace.capabilities.builtin import build_registry
    class Model:
        def complete(self, system, message):
            return '{"summary":"实验设计","artifacts":[{"type":"Experiment","content":{"title":"反射实验","component_type":"light_reflection_v1"}}],"warnings":[]}'
    registry = build_registry(Model())
    result = registry.invoke('activity.design@1', {}, {'goal': '反射', 'parameters': {}, 'dependencies': {}})
    assert result['artifacts'][0]['type'] == 'Experiment'
    assert result['sources'] == []


def test_builtin_rejects_untrusted_component():
    from app.workspace.capabilities.builtin import build_registry
    class Model:
        def complete(self, system, message):
            return '{"summary":"x","artifacts":[{"type":"Experiment","content":{"component_type":"shell"}}],"warnings":[]}'
    with pytest.raises(ValueError, match='component'):
        build_registry(Model()).invoke('activity.design@1', {}, {'goal': '反射', 'parameters': {}, 'dependencies': {}})


def test_curriculum_capability_uses_server_settings_and_current_permissions(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase
    from app.workspace.integrations import rag
    from app.workspace.capabilities.builtin import build_registry
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as db:
        rag.set_allowed_experts(db, ['physics_teacher_agent'])
    monkeypatch.setattr(rag.CurriculumPermissionService, 'allowed_sources', lambda db, expert_id, role_category: ['authorized.md'])
    monkeypatch.setattr(rag, 'filter_curriculum_sources', lambda db, sources: sources, raising=False)
    monkeypatch.setattr(rag.RagService, 'retrieve_curriculum_context', lambda db, **kwargs: ('课标片段', {'mode': 'local_bm25', 'hit_sources': ['authorized.md'], 'records': [{'source': 'authorized.md', 'chunk_id': 1}]}))
    registry = build_registry(None, factory)
    result = registry.invoke('knowledge.retrieve@1', {'workspace_id': 'w', 'run_id': 'r', 'user_id': 't'}, {'goal': '反射', 'parameters': {'expert_id': 'physics_teacher_agent'}, 'dependencies': {}})
    assert result['summary'] == '课标片段'
    assert result['sources'] == [{'expert_id': 'physics_teacher_agent', 'source': 'authorized.md'}]
    engine.dispose()

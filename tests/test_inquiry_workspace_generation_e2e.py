import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import CurriculumSourceAgentPermissionModel, CurriculumSourceModel, UserModel, UserWorkspaceRoleModel
from app.workspace.api import get_workspace, make_snapshot, snapshot_print
from app.workspace.artifacts.service import create_workspace
from app.workspace.integrations.rag import set_allowed_experts
from app.workspace.models import WorkspaceBase, WorkspaceRagAudit, WorkspaceRun
from app.workspace.runtime.runs import create_run
from app.workspace.runtime.worker import WorkspaceWorker


def n(id, capability, depends=(), inputs=None):
    return {'id': id, 'capability': capability, 'depends_on': list(depends), 'inputs': inputs or {}}


def test_generation_uses_authorized_curriculum_and_revocation_blocks_snapshot(tmp_path, monkeypatch):
    from app.services.rag_service import RagService
    engine = create_engine(f'sqlite:///{(tmp_path / "e2e.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    for table in (UserModel.__table__, UserWorkspaceRoleModel.__table__, CurriculumSourceModel.__table__, CurriculumSourceAgentPermissionModel.__table__):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(UserModel(id='t', username='teacher', password_hash='x', user_role='teacher', created_at='now'))
        db.add(UserWorkspaceRoleModel(user_id='t', role_category='teacher', created_at='now'))
        db.add(CurriculumSourceModel(source='standard.md', category='curriculum', updated_at='now'))
        db.add(CurriculumSourceAgentPermissionModel(source='standard.md', agent_id='physics_teacher_agent', role_category='teacher', created_at='now'))
        set_allowed_experts(db, ['physics_teacher_agent'])
        workspace = create_workspace(db, 't', '光的反射')
        workspace_id = workspace.id
        run_id = create_run(db, workspace.id, 't', '光的反射教学设计', 'lesson', 'key').id
    def retrieve(db, **kwargs):
        assert kwargs['allowed_sources'] == ['standard.md']
        return '相关标准内容', {'mode': 'local_bm25', 'hit_sources': ['standard.md'], 'records': [{'source': 'standard.md', 'chunk_id': 1}]}
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', retrieve)
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version': 1, 'goal': '光的反射', 'nodes': [
                    n('rag', 'knowledge.retrieve@1', inputs={'expert_id': 'physics_teacher_agent'}),
                    n('goal', 'goals.compose@1', ['rag']), n('question', 'inquiry.design@1', ['goal']),
                    n('activity', 'activity.design@1', ['goal', 'question']),
                    n('assessment', 'assessment.design@1', ['goal', 'activity']),
                    n('quality', 'quality.evaluate@1', ['goal', 'question', 'activity', 'assessment']),
                ]}, ensure_ascii=False)
            capability = next(name for name in ('goals.compose@1','inquiry.design@1','activity.design@1','assessment.design@1','quality.evaluate@1') if name in system)
            data = json.loads(message)
            refs = data['dependencies'].get('goal', {}).get('artifact_refs', [])
            ids = [item['id'] for item in refs]
            artifacts = {
                'goals.compose@1': [{'type': 'LearningGoal', 'content': {'title': '理解规律', 'description': '比较两个角'}}],
                'inquiry.design@1': [{'type': 'InquiryQuestion', 'content': {'title': '问题', 'question': '两个角有什么关系？'}}],
                'activity.design@1': [{'type': 'Experiment', 'content': {'title': '反射实验', 'description': '观察光线', 'materials': ['镜子'], 'safety_measures': ['成人监督'], 'component_type': 'light_reflection_v1'}}, {'type': 'InquiryActivity', 'content': {'title': '记录数据', 'description': '比较角度', 'goal_ids': ids}}],
                'assessment.design@1': [{'type': 'Assessment', 'content': {'title': '评价', 'criteria': ['能比较角度'], 'goal_ids': ids}}],
                'quality.evaluate@1': [],
            }[capability]
            return json.dumps({'summary': '已完成', 'artifacts': artifacts, 'warnings': []}, ensure_ascii=False)
    assert WorkspaceWorker(factory, Model()).process_next()
    teacher = SimpleNamespace(id='t', user_role='teacher')
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        assert db.query(WorkspaceRagAudit).filter_by(run_id=run_id).count() == 1
        workspace = get_workspace(workspace_id, db, teacher)['data']
        assert {'LearningGoal', 'InquiryQuestion', 'Experiment', 'Assessment'}.issubset({a['type'] for a in workspace['artifacts']})
        assert any(a['source_refs'] for a in workspace['artifacts'])
        snapshot_id = make_snapshot(workspace_id, db, teacher)['data']['id']
        assert snapshot_print(workspace_id, snapshot_id, db, teacher)['data']['sections']
    with factory.begin() as db:
        db.query(CurriculumSourceAgentPermissionModel).filter_by(source='standard.md', agent_id='physics_teacher_agent').delete()
    with factory() as db:
        with pytest.raises(HTTPException) as error:
            snapshot_print(workspace_id, snapshot_id, db, teacher)
        assert error.value.status_code == 403
    engine.dispose()


def test_curriculum_revoked_during_model_call_blocks_commit_and_trace(tmp_path, monkeypatch):
    import threading
    from app.workspace.api import get_run
    from app.workspace.runtime.runs import execute_builtin_run
    from app.workspace.models import Artifact
    from app.services.rag_service import RagService
    engine = create_engine(f'sqlite:///{(tmp_path / "revoked.db").as_posix()}', connect_args={'check_same_thread': False})
    WorkspaceBase.metadata.create_all(engine)
    for table in (UserModel.__table__, UserWorkspaceRoleModel.__table__, CurriculumSourceModel.__table__, CurriculumSourceAgentPermissionModel.__table__):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(UserModel(id='t', username='teacher', password_hash='x', user_role='teacher', created_at='now'))
        db.add(UserWorkspaceRoleModel(user_id='t', role_category='teacher', created_at='now'))
        db.add(CurriculumSourceModel(source='standard.md', category='curriculum', updated_at='now'))
        db.flush()
        db.add(CurriculumSourceAgentPermissionModel(source='standard.md', agent_id='physics_teacher_agent', role_category='teacher', created_at='now'))
        set_allowed_experts(db, ['physics_teacher_agent'])
        workspace = create_workspace(db, 't', '反射')
        workspace_id = workspace.id
        run_id = create_run(db, workspace.id, 't', '反射实验', 'experiment', 'key').id
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', lambda db, **kwargs: ('授权内容', {'mode':'local_bm25', 'hit_sources':['standard.md'], 'records':[{'source':'standard.md', 'chunk_id':1}]}))
    started, release = threading.Event(), threading.Event()
    class Model:
        def complete(self, system, message):
            if '规划器' in system:
                return json.dumps({'version':1, 'goal':'反射实验', 'nodes':[n('rag','knowledge.retrieve@1', inputs={'expert_id':'physics_teacher_agent'}), n('experiment','activity.design@1',['rag'])]})
            started.set(); assert release.wait(5)
            return '{"summary":"实验","artifacts":[{"type":"Experiment","content":{"title":"反射","description":"观察","materials":["镜子"],"safety_measures":["监督"]}}],"warnings":[]}'
    thread = threading.Thread(target=execute_builtin_run, args=(factory, run_id, Model()))
    thread.start(); assert started.wait(5)
    with factory.begin() as db:
        db.query(CurriculumSourceAgentPermissionModel).filter_by(source='standard.md', agent_id='physics_teacher_agent').delete()
    release.set(); thread.join(5)
    assert not thread.is_alive()
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'failed'
        assert db.query(Artifact).count() == 0
        with pytest.raises(HTTPException) as error:
            get_run(workspace_id, run_id, db, SimpleNamespace(id='t', user_role='teacher'))
        assert error.value.status_code == 403
    engine.dispose()

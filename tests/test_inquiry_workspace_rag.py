from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.workspace.models import WorkspaceBase, WorkspaceRagAudit
from app.workspace.integrations.rag import retrieve_authorized, set_allowed_experts, get_allowed_experts
from app.workspace.integrations.rag import assert_sources_authorized


def test_settings_accept_only_selectable_teacher_experts():
    import pytest
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine) as db:
        assert get_allowed_experts(db) == []
        assert set_allowed_experts(db, ['physics_teacher_agent']) == ['physics_teacher_agent']
        assert get_allowed_experts(db) == ['physics_teacher_agent']
        with pytest.raises(ValueError):
            set_allowed_experts(db, ['main_tutor'])
    engine.dispose()


def test_rag_uses_only_configured_expert_authorization_and_audits(monkeypatch):
    from app.services.curriculum_permission_service import CurriculumPermissionService
    from app.services.rag_service import RagService
    from app.workspace.integrations import rag

    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    calls = []
    monkeypatch.setattr(CurriculumPermissionService, 'allowed_sources', lambda db, expert_id, role_category: ['allowed.md'])
    monkeypatch.setattr(rag, 'filter_curriculum_sources', lambda db, sources: sources, raising=False)
    def fake_retrieve(db, **kwargs):
        calls.append(kwargs)
        return '授权证据', {'mode': 'local_bm25', 'query': '光', 'hit_sources': ['allowed.md'], 'records': [{'source': 'allowed.md', 'chunk_id': 3}]}
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', fake_retrieve)
    with Session(engine) as db:
        context, metadata = retrieve_authorized(db, workspace_id='ws', run_id='run', user_id='teacher', expert_id='physics_teacher_agent', configured_experts=['physics_teacher_agent'], query='光')
        assert context == '授权证据'
        assert calls[0]['allowed_sources'] == ['allowed.md']
        assert calls[0]['role_category'] == 'teacher'
        assert metadata['hit_sources'] == ['allowed.md']
        assert db.query(WorkspaceRagAudit).one().expert_id == 'physics_teacher_agent'
        context, metadata = retrieve_authorized(db, workspace_id='ws', run_id='run', user_id='teacher', expert_id='nature_agent', configured_experts=['physics_teacher_agent'], query='光')
        assert context == '' and metadata['mode'] == 'expert_not_configured'
        assert len(calls) == 1
        assert db.query(WorkspaceRagAudit).count() == 2
    engine.dispose()


def test_curriculum_search_excludes_authorized_ecology_sources(monkeypatch):
    from app.db.models import CurriculumSourceModel
    from app.services.curriculum_permission_service import CurriculumPermissionService
    from app.services.rag_service import RagService
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    CurriculumSourceModel.__table__.create(engine)
    calls = []
    monkeypatch.setattr(CurriculumPermissionService, 'allowed_sources', lambda db, expert_id, role_category: ['curriculum.md', 'ecology.md'])
    def retrieve(db, **kwargs):
        calls.append(kwargs['allowed_sources'])
        return '', {'mode': 'local_bm25_empty', 'hit_sources': [], 'records': []}
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', retrieve)
    with Session(engine) as db:
        db.add_all([CurriculumSourceModel(source='curriculum.md', category='curriculum', updated_at='now'),
                    CurriculumSourceModel(source='ecology.md', category='ecology', updated_at='now')])
        db.flush()
        retrieve_authorized(db, workspace_id='w', run_id='r', user_id='t', expert_id='physics_teacher_agent', configured_experts=['physics_teacher_agent'], query='光')
        assert calls == [['curriculum.md']]
    engine.dispose()


def test_revoked_sources_are_denied_for_historical_content(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.services.curriculum_permission_service import CurriculumPermissionService
    from app.workspace.integrations import rag
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    allowed = ['curriculum.md']
    monkeypatch.setattr(CurriculumPermissionService, 'allowed_sources', lambda db, expert_id, role_category: allowed)
    monkeypatch.setattr(rag, 'filter_curriculum_sources', lambda db, sources: sources)
    with Session(engine) as db:
        set_allowed_experts(db, ['physics_teacher_agent'])
        sources = [{'expert_id': 'physics_teacher_agent', 'source': 'curriculum.md'}]
        assert_sources_authorized(db, sources)
        allowed.clear()
        with pytest.raises(HTTPException) as error:
            assert_sources_authorized(db, sources)
        assert error.value.status_code == 403
    engine.dispose()


def test_revoked_source_blocks_workspace_and_export_snapshot(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.db.models import UserWorkspaceRoleModel
    from app.services.curriculum_permission_service import CurriculumPermissionService
    from app.workspace.api import get_workspace, make_snapshot, snapshot_print
    from app.workspace.artifacts.service import create_workspace, _create_artifact
    from app.workspace.integrations import rag
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    UserWorkspaceRoleModel.__table__.create(engine)
    allowed = ['curriculum.md']
    monkeypatch.setattr(CurriculumPermissionService, 'allowed_sources', lambda db, expert_id, role_category: allowed)
    monkeypatch.setattr(rag, 'filter_curriculum_sources', lambda db, sources: sources)
    with Session(engine, expire_on_commit=False) as db:
        db.add(UserWorkspaceRoleModel(user_id='t', role_category='teacher', created_at='now'))
        set_allowed_experts(db, ['physics_teacher_agent'])
        workspace = create_workspace(db, 't', '反射')
        _create_artifact(db, workspace.id, 'ReportNarrative', {'section_key': 'teaching_context', 'title': '依据', 'paragraphs': ['来自课标']}, sources=[{'expert_id': 'physics_teacher_agent', 'source': 'curriculum.md'}])
        db.commit()
        user = SimpleNamespace(id='t', user_role='teacher')
        snapshot_id = make_snapshot(workspace.id, db, user)['data']['id']
        assert snapshot_print(workspace.id, snapshot_id, db, user)['data']['sections']
        allowed.clear()
        with pytest.raises(HTTPException) as error:
            get_workspace(workspace.id, db, user)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            snapshot_print(workspace.id, snapshot_id, db, user)
        assert error.value.status_code == 403
    engine.dispose()


def test_experiment_records_inherit_source_lineage():
    import json
    from app.workspace.artifacts.service import create_workspace, _create_artifact, record_reflection
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 't', '反射')
        sources = [{'expert_id': 'physics_teacher_agent', 'source': 'curriculum.md'}]
        experiment = _create_artifact(db, workspace.id, 'Experiment', {'component_type': 'light_reflection_v1'}, sources=sources)
        record = record_reflection(db, workspace.id, experiment.id, 30, None, 'k')
        assert json.loads(record.source_json) == sources
    engine.dispose()

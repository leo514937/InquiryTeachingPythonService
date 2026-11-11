import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import CurriculumSourceModel
from app.workspace.models import WorkspaceBase


@pytest.fixture
def scope_db(monkeypatch):
    from app.services.curriculum_permission_service import CurriculumPermissionService
    from app.workspace.integrations import rag
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    permissions = {'a.md', 'b.md'}
    monkeypatch.setattr(CurriculumPermissionService, 'allowed_sources',
                        lambda db, expert_id, role_category: list(permissions))
    monkeypatch.setattr(rag, 'get_allowed_experts', lambda db: ['physics_teacher_agent'])
    with Session(engine) as db:
        db.add_all([CurriculumSourceModel(source='a.md', id='a', category='curriculum', title='A', updated_at='now'),
                    CurriculumSourceModel(source='b.md', id='b', category='curriculum', title='B', updated_at='now'),
                    CurriculumSourceModel(source='c.md', id='c', category='curriculum', title='C', updated_at='now'),
                    CurriculumSourceModel(source='e.md', id='e', category='ecology', title='E', updated_at='now')])
        db.flush()
        yield db, permissions
    engine.dispose()


def test_selection_resolves_only_explicitly_selected_authorized_sources(scope_db):
    from app.workspace.integrations.rag import resolve_selected_sources
    db, _ = scope_db
    expert, rows = resolve_selected_sources(db, ['b', 'a'])
    assert expert == 'physics_teacher_agent'
    assert [row.source for row in rows] == ['b.md', 'a.md']
    assert resolve_selected_sources(db, [])[1] == []


@pytest.mark.parametrize('ids', [['c'], ['missing'], ['e'], ['a', 'a']])
def test_selection_rejects_unauthorized_missing_wrong_category_and_duplicates(scope_db, ids):
    from app.workspace.integrations.rag import resolve_selected_sources
    from fastapi import HTTPException
    db, _ = scope_db
    with pytest.raises(HTTPException) as error:
        resolve_selected_sources(db, ids)
    assert error.value.status_code in (403, 422)


def test_selection_rechecks_revoked_permission(scope_db):
    from app.workspace.integrations.rag import resolve_selected_sources
    from fastapi import HTTPException
    db, permissions = scope_db
    resolve_selected_sources(db, ['a'])
    permissions.remove('a.md')
    with pytest.raises(HTTPException) as error:
        resolve_selected_sources(db, ['a'])
    assert error.value.status_code == 403


def test_selected_retrieval_limits_scope_and_does_not_search_when_empty(scope_db, monkeypatch):
    from app.services.rag_service import RagService
    from app.workspace.integrations.rag import retrieve_selected_sources
    from app.workspace.models import WorkspaceRagAudit
    db, _ = scope_db
    calls = []
    def retrieve(db, **kwargs):
        calls.append(kwargs['allowed_sources'])
        return 'A evidence', {'mode': 'local_bm25', 'hit_sources': ['a.md'],
                              'records': [{'source': 'a.md', 'chunk_id': 1}]}
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', retrieve)
    kwargs = dict(workspace_id='w', run_id='r', user_id='u', query='目标')
    _, result = retrieve_selected_sources(db, source_ids=['a'], **kwargs)
    assert result['hit_sources'] == ['a.md']
    assert calls == [['a.md']]
    _, result = retrieve_selected_sources(db, source_ids=[], **kwargs)
    assert result['mode'] == 'no_sources'
    assert calls == [['a.md']]
    assert db.query(WorkspaceRagAudit).count() == 1


def test_selected_retrieval_rejects_out_of_scope_hits(scope_db, monkeypatch):
    from app.services.rag_service import RagService
    from app.workspace.integrations.rag import retrieve_selected_sources
    db, _ = scope_db
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', lambda db, **kwargs:
                        ('B evidence', {'mode': 'local_bm25', 'hit_sources': ['b.md'],
                                        'records': [{'source': 'b.md', 'chunk_id': 2}]}))
    text, result = retrieve_selected_sources(db, workspace_id='w', run_id='r', user_id='u',
                                             query='目标', source_ids=['a'])
    assert text == ''
    assert result['mode'] == 'permission_error'
    assert result['records'] == []


def test_multiple_sources_and_subsequent_deselection_change_retrieval_scope(scope_db, monkeypatch):
    from app.services.rag_service import RagService
    from app.workspace.integrations.rag import retrieve_selected_sources
    db, _ = scope_db
    calls = []
    def retrieve(db, **kwargs):
        allowed = kwargs['allowed_sources']
        calls.append(set(allowed))
        return '', {'mode': 'local_bm25_empty', 'hit_sources': [], 'records': []}
    monkeypatch.setattr(RagService, 'retrieve_curriculum_context', retrieve)
    kwargs = dict(workspace_id='w', run_id='r', user_id='u', query='目标')
    retrieve_selected_sources(db, source_ids=['a', 'b'], **kwargs)
    retrieve_selected_sources(db, source_ids=['a'], **kwargs)
    assert calls == [{'a.md', 'b.md'}, {'a.md'}]

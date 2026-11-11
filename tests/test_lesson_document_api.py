from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import UserWorkspaceRoleModel
from app.workspace.models import WorkspaceBase


@pytest.fixture
def context():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([UserWorkspaceRoleModel(user_id='teacher', role_category='teacher', created_at='now'),
                    UserWorkspaceRoleModel(user_id='other', role_category='teacher', created_at='now')])
        db.commit()
        yield db, SimpleNamespace(id='teacher', user_role='teacher'), SimpleNamespace(id='other', user_role='teacher')
    engine.dispose()


def test_import_save_conflict_history_and_export(context):
    from docx import Document
    from app.workspace.api import (CreateWorkspace, add_workspace, LessonImport, LessonSave,
        add_lesson_document, save_lesson_document, artifact_versions, lesson_document_docx)
    db, teacher, other = context
    ws = add_workspace(CreateWorkspace(title='校园'), db, teacher)['data']['id']
    original = '标题\n教学目标\n原始目标\n未知章节\n保留内容'
    item = add_lesson_document(ws, LessonImport(title='教案', text=original), db, teacher)['data']
    assert '\n'.join(p['text'] for s in item['content']['sections'] for p in s['paragraphs']) == original
    assert [s['title'] for s in item['content']['sections']] == ['教案原文', '教学目标']
    assert item['version'] == 1
    updated = item['content'].copy()
    updated['sections'][0]['paragraphs'][0]['text'] = '教师修改'
    saved = save_lesson_document(ws, item['id'], LessonSave(expected_version=1, content=updated), db, teacher)['data']
    assert saved['version'] == 2
    with pytest.raises(HTTPException) as conflict:
        save_lesson_document(ws, item['id'], LessonSave(expected_version=1, content=updated), db, teacher)
    assert conflict.value.status_code == 409
    versions = artifact_versions(ws, item['id'], db, teacher)['data']
    assert versions[0]['content']['sections'][0]['paragraphs'][0]['text'] == '标题'
    assert versions[1]['content']['sections'][0]['paragraphs'][0]['text'] == '教师修改'
    exported = lesson_document_docx(ws, item['id'], db, teacher)
    assert '教师修改' in [p.text for p in Document(BytesIO(exported.body)).paragraphs]
    with pytest.raises(HTTPException) as denied:
        lesson_document_docx(ws, item['id'], db, other)
    assert denied.value.status_code == 404


def test_lesson_document_cannot_be_updated_through_generic_artifact_api(context):
    from app.workspace.api import (CreateWorkspace, add_workspace, LessonImport, ArtifactUpdate,
                                   add_lesson_document, edit_record)
    db, teacher, _ = context
    ws = add_workspace(CreateWorkspace(title='校园'), db, teacher)['data']['id']
    item = add_lesson_document(ws, LessonImport(title='教案', text='正文'), db, teacher)['data']
    with pytest.raises(HTTPException) as denied:
        edit_record(ws, item['id'], ArtifactUpdate(expected_version=1, content={'forged': True}), db, teacher)
    assert denied.value.status_code == 409


def test_locked_lesson_cannot_be_restored(context):
    from app.workspace.api import (CreateWorkspace, add_workspace, LessonImport, ArtifactRestore,
                                   add_lesson_document, restore_version)
    from app.workspace.models import Artifact
    db, teacher, _ = context
    ws = add_workspace(CreateWorkspace(title='校园'), db, teacher)['data']['id']
    item = add_lesson_document(ws, LessonImport(title='教案', text='正文'), db, teacher)['data']
    db.get(Artifact, item['id']).locked = 1
    db.commit()
    with pytest.raises(HTTPException) as denied:
        restore_version(ws, item['id'], ArtifactRestore(expected_version=1, version=1), db, teacher)
    assert denied.value.status_code == 409


def test_lesson_save_rejects_removing_referenced_paragraph_ids(context):
    from app.workspace.api import (CreateWorkspace, add_workspace, LessonImport, LessonSave,
                                   add_lesson_document, save_lesson_document)
    from app.workspace.models import ArtifactDependency
    db, teacher, _ = context
    ws = add_workspace(CreateWorkspace(title='校园'), db, teacher)['data']['id']
    item = add_lesson_document(ws, LessonImport(title='教案', text='正文'), db, teacher)['data']
    db.add(ArtifactDependency(workspace_id=ws, upstream_id=item['id'], upstream_version=1,
                              upstream_field='/sections', downstream_id='dependent', downstream_field=''))
    db.commit()
    changed = item['content']
    changed['sections'][0]['paragraphs'][0]['id'] = 'replacement'
    with pytest.raises(HTTPException) as denied:
        save_lesson_document(ws, item['id'], LessonSave(expected_version=1, content=changed), db, teacher)
    assert denied.value.status_code == 409



import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.workspace.models import WorkspaceBase
from app.workspace.artifacts.service import create_workspace, create_experiment, record_reflection, include_reflection_in_report
from app.workspace.reports.service import create_narrative, update_narrative, create_snapshot, read_snapshot


def test_report_snapshot_keeps_exact_narrative_version():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '光的反射')
        narrative = create_narrative(db, workspace.id, 'teaching_context', '学情与设计说明', ['原始段落'])
        before = create_snapshot(db, workspace.id)
        updated = update_narrative(db, workspace.id, narrative.id, 1, ['教师修改后的段落'])
        after = create_snapshot(db, workspace.id)
        assert updated.version == 2
        assert read_snapshot(db, workspace.id, before.id)['sections'][0]['paragraphs'] == ['原始段落']
        assert read_snapshot(db, workspace.id, after.id)['sections'][0]['paragraphs'] == ['教师修改后的段落']
        with pytest.raises(ValueError, match='version'):
            update_narrative(db, workspace.id, narrative.id, 1, ['过时修改'])
    engine.dispose()


def test_reflection_records_are_included_only_when_selected():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '光的反射')
        experiment = create_experiment(db, workspace.id)
        record = record_reflection(db, workspace.id, experiment.id, 30, None, 'key')
        before = create_snapshot(db, workspace.id)
        assert all(s['title'] != '实验记录与观察' for s in read_snapshot(db, workspace.id, before.id)['sections'])
        include_reflection_in_report(db, workspace.id, record.id, 1, True)
        after = create_snapshot(db, workspace.id)
        assert any(s['title'] == '实验记录与观察' for s in read_snapshot(db, workspace.id, after.id)['sections'])
    engine.dispose()


def test_report_orders_context_before_experiment_and_records():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '光的反射')
        experiment = create_experiment(db, workspace.id)
        record = record_reflection(db, workspace.id, experiment.id, 30, None, 'key')
        include_reflection_in_report(db, workspace.id, record.id, 1, True)
        create_narrative(db, workspace.id, 'teaching_context', '学情与设计说明', ['说明'])
        snapshot = create_snapshot(db, workspace.id)
        assert [s['title'] for s in read_snapshot(db, workspace.id, snapshot.id)['sections']] == ['学情与设计说明', '光的反射交互实验', '实验记录与观察']
    engine.dispose()


def test_report_projects_generated_teaching_objects():
    from app.workspace.artifacts.service import _create_artifact
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '反射')
        _create_artifact(db, workspace.id, 'Assessment', {'title': '形成性评价', 'description': '比较角度'})
        _create_artifact(db, workspace.id, 'LearningGoal', {'title': '理解反射定律', 'description': '比较入射角和反射角'})
        _create_artifact(db, workspace.id, 'InquiryQuestion', {'title': '探究问题', 'question': '两角有什么关系？'})
        snapshot = create_snapshot(db, workspace.id)
        sections = read_snapshot(db, workspace.id, snapshot.id)['sections']
        assert [s['title'] for s in sections] == ['理解反射定律', '探究问题', '形成性评价']
        assert sections[0]['paragraphs'] == ['比较入射角和反射角']
    engine.dispose()


@pytest.mark.parametrize('status', ['queued', 'running', 'waiting_review', 'failed', 'cancelled'])
def test_snapshot_rejects_unfinished_or_unreviewed_generated_content(status):
    from app.workspace.artifacts.service import _create_artifact
    from app.workspace.runtime.runs import create_run
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '反射')
        run = create_run(db, workspace.id, 'teacher', '需求', 'experiment', 'key')
        run.status = status
        _create_artifact(db, workspace.id, 'Experiment', {'title': '实验'}, author_kind='agent', run_id=run.id)
        with pytest.raises(ValueError, match='审核'):
            create_snapshot(db, workspace.id)
    engine.dispose()


def test_restore_keeps_review_constraints_from_both_versions():
    from app.workspace.artifacts.service import _create_artifact, _save_version, restore_artifact
    from app.workspace.runtime.runs import create_run, cancel_run
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '反射')
        first = create_run(db, workspace.id, 'teacher', '旧内容', 'experiment', 'first')
        artifact = _create_artifact(db, workspace.id, 'Experiment', {'title': '待审核内容'}, author_kind='agent', run_id=first.id)
        cancel_run(db, first.id)
        second = create_run(db, workspace.id, 'teacher', '新内容', 'experiment', 'second')
        second.status = 'completed'
        _save_version(db, artifact, 1, {'title': '已完成内容'}, author_kind='agent', run_id=second.id)
        restore_artifact(db, workspace.id, artifact.id, 2, 1)
        with pytest.raises(ValueError, match='审核'):
            create_snapshot(db, workspace.id)
    engine.dispose()

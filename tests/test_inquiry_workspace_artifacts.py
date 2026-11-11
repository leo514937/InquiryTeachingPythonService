import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.workspace.artifacts.service import create_workspace, create_experiment, update_artifact, restore_artifact
from app.workspace.models import ArtifactVersion, WorkspaceBase


def test_artifact_edit_and_restore_preserve_versions_and_lineage():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '光的反射')
        artifact = create_experiment(db, workspace.id)
        original = artifact.content.copy()
        edited = update_artifact(db, workspace.id, artifact.id, 1, {**original, 'title': '手电筒实验'})
        assert edited.version == 2 and edited.content['title'] == '手电筒实验'
        with pytest.raises(ValueError, match='version'):
            update_artifact(db, workspace.id, artifact.id, 1, original)
        restored = restore_artifact(db, workspace.id, artifact.id, 2, 1)
        assert restored.version == 3 and restored.content == original
        assert db.query(ArtifactVersion).filter_by(artifact_id=artifact.id).count() == 3
    engine.dispose()


def test_cannot_bind_unknown_experiment_component():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '光的反射')
        artifact = create_experiment(db, workspace.id)
        with pytest.raises(ValueError, match='component'):
            update_artifact(db, workspace.id, artifact.id, 1, {'component_type': 'arbitrary_code'})
    engine.dispose()


def test_field_impact_only_marks_dependent_objects_and_preserves_locked():
    from app.workspace.artifacts.service import _create_artifact
    from app.workspace.models import ArtifactDependency
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '反射')
        experiment = create_experiment(db, workspace.id)
        activity = _create_artifact(db, workspace.id, 'InquiryActivity', {'title': '活动'}, author_kind='agent')
        other = _create_artifact(db, workspace.id, 'Assessment', {'title': '评价'}, author_kind='agent')
        locked = _create_artifact(db, workspace.id, 'ReportNarrative', {'title': '说明'}, author_kind='agent')
        locked.locked = 1
        db.add_all([
            ArtifactDependency(workspace_id=workspace.id, upstream_id=experiment.id, upstream_version=1, upstream_field='/materials', downstream_id=activity.id, downstream_field=''),
            ArtifactDependency(workspace_id=workspace.id, upstream_id=experiment.id, upstream_version=1, upstream_field='/description', downstream_id=other.id, downstream_field=''),
            ArtifactDependency(workspace_id=workspace.id, upstream_id=activity.id, upstream_version=1, upstream_field='', downstream_id=locked.id, downstream_field=''),
        ])
        db.flush()
        update_artifact(db, workspace.id, experiment.id, 1, {**experiment.content, 'materials': ['手电筒']})
        db.refresh(activity); db.refresh(other); db.refresh(locked)
        assert activity.status == 'stale'
        assert other.status == 'active'
        assert locked.review_status == 'needs_review'
        assert locked.content['title'] == '说明'
    engine.dispose()


def test_replan_targets_only_stale_unlocked_generated_dependents():
    import json
    from app.workspace.artifacts.service import _create_artifact
    from app.workspace.models import ArtifactDependency
    from app.workspace.runtime.replan import prepare_replan
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 'teacher', '反射')
        source = create_experiment(db, workspace.id)
        target = _create_artifact(db, workspace.id, 'InquiryActivity', {'title': '活动'}, author_kind='agent')
        locked = _create_artifact(db, workspace.id, 'Assessment', {'title': '评价'}, author_kind='agent')
        locked.locked = 1
        db.add_all([
            ArtifactDependency(workspace_id=workspace.id, upstream_id=source.id, upstream_version=1, upstream_field='/materials', downstream_id=target.id, downstream_field=''),
            ArtifactDependency(workspace_id=workspace.id, upstream_id=source.id, upstream_version=1, upstream_field='/materials', downstream_id=locked.id, downstream_field=''),
        ])
        db.flush()
        update_artifact(db, workspace.id, source.id, 1, {**source.content, 'materials': ['手电筒']})
        payload = prepare_replan(db, workspace.id, source.id)
        assert [item['id'] for item in payload['targets']] == [target.id]
        assert locked.id in payload['requires_review']
        assert json.loads(source.change_paths_json) == ['/materials']
    engine.dispose()


def test_teacher_can_lock_and_unlock_with_version_guard():
    from app.workspace.artifacts.service import set_artifact_lock
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db, 't', '反射')
        artifact = create_experiment(db, workspace.id)
        locked = set_artifact_lock(db, workspace.id, artifact.id, 1, True)
        assert locked.locked == 1 and locked.version == 2
        with pytest.raises(ValueError, match='version'):
            set_artifact_lock(db, workspace.id, artifact.id, 1, False)
        unlocked = set_artifact_lock(db, workspace.id, artifact.id, 2, False)
        assert unlocked.locked == 0 and unlocked.version == 3
    engine.dispose()

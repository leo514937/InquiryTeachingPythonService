import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.workspace.models import WorkspaceBase
from app.workspace.artifacts.service import create_workspace, create_experiment, record_reflection, update_observation, delete_reflection_record


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def test_reflection_records_are_versioned_and_recomputed(db):
    workspace = create_workspace(db, 'teacher-1', '光的反射')
    experiment = create_experiment(db, workspace.id)
    record = record_reflection(db, workspace.id, experiment.id, 30, None, 'key-1')
    assert record.content['records'][0]['reflected_angle_deg'] == 30
    same = record_reflection(db, workspace.id, experiment.id, 30, None, 'key-1')
    assert same.version == 1
    record = record_reflection(db, workspace.id, experiment.id, 45, 1, 'key-2')
    assert record.version == 2
    assert [r['incident_angle_deg'] for r in record.content['records']] == [30, 45]
    record = update_observation(db, workspace.id, record.id, 2, '入射角等于反射角')
    assert record.version == 3
    assert record.content['conclusion'] == '入射角等于反射角'


@pytest.mark.parametrize('angle', [-1, 81, 1.5])
def test_invalid_reflection_angle_rejected(db, angle):
    workspace = create_workspace(db, 'teacher-1', '光的反射')
    experiment = create_experiment(db, workspace.id)
    with pytest.raises(ValueError):
        record_reflection(db, workspace.id, experiment.id, angle, None, 'key')


def test_reflection_record_requires_matching_version(db):
    workspace = create_workspace(db, 'teacher-1', '光的反射')
    experiment = create_experiment(db, workspace.id)
    record_reflection(db, workspace.id, experiment.id, 30, None, 'key-1')
    with pytest.raises(ValueError, match='version'):
        record_reflection(db, workspace.id, experiment.id, 60, 0, 'key-2')


def test_experiment_can_have_only_one_record_artifact(db):
    from app.workspace.models import Artifact
    workspace = create_workspace(db, 'teacher-1', '光的反射')
    experiment = create_experiment(db, workspace.id)
    record_reflection(db, workspace.id, experiment.id, 30, None, 'key-1')
    db.add(Artifact(id='duplicate', workspace_id=workspace.id, type='DataRecord', parent_id=experiment.id, version=1, content_json='{}'))
    with pytest.raises(IntegrityError):
        db.flush()


def test_record_delete_creates_a_new_version(db):
    from app.workspace.models import ArtifactVersion
    workspace = create_workspace(db, 'teacher-1', '光的反射')
    experiment = create_experiment(db, workspace.id)
    record = record_reflection(db, workspace.id, experiment.id, 30, None, 'key')
    record_id = record.content['records'][0]['id']
    updated = delete_reflection_record(db, workspace.id, record.id, 1, record_id)
    assert updated.version == 2 and updated.content['records'] == []
    assert db.query(ArtifactVersion).filter_by(artifact_id=record.id).count() == 2

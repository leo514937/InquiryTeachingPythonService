import json

from app.workspace.artifacts.dependencies import affected_artifact_ids
from app.workspace.integrations.rag import assert_sources_authorized
from app.workspace.models import Artifact, ArtifactDependency, ArtifactVersion


def prepare_replan(db, workspace_id, artifact_id, *, mark_review=True):
    source = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id).first()
    if not source:
        raise LookupError('artifact not found')
    assert_sources_authorized(db, json.loads(source.source_json))
    affected = affected_artifact_ids(db, workspace_id, artifact_id, set(json.loads(source.change_paths_json)))
    targets, review = [], []
    rows = db.query(Artifact).filter(Artifact.workspace_id == workspace_id, Artifact.id.in_(affected)).order_by(Artifact.order_index, Artifact.id).all()
    barriers = set()
    for row in rows:
        assert_sources_authorized(db, json.loads(row.source_json))
        version = db.query(ArtifactVersion).filter_by(artifact_id=row.id, version=row.version).first()
        if row.locked or row.review_status in ('approved', 'needs_review') or not version or version.author_kind != 'agent':
            barriers.add(row.id)
    edges = db.query(ArtifactDependency).filter_by(workspace_id=workspace_id).all()
    blocked = set(barriers)
    while True:
        more = {edge.downstream_id for edge in edges if edge.upstream_id in blocked and edge.downstream_id in affected}
        if more <= blocked:
            break
        blocked.update(more)
    for row in rows:
        if row.id in blocked:
            if mark_review:
                row.review_status = 'needs_review'
            review.append(row.id)
        elif row.status == 'stale':
            targets.append({'id': row.id, 'version': row.version, 'type': row.type, 'content': row.content,
                            'sources': json.loads(row.source_json)})
    target_ids = {item['id'] for item in targets}
    edges = [{'upstream_id': edge.upstream_id, 'downstream_id': edge.downstream_id}
             for edge in edges
             if edge.upstream_id in target_ids and edge.downstream_id in target_ids]
    return {'root': {'id': source.id, 'version': source.version, 'type': source.type, 'content': source.content,
                     'sources': json.loads(source.source_json)}, 'targets': targets, 'requires_review': review, 'edges': edges}

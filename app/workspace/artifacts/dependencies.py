"""Field-aware impact tracking for workspace artifacts."""
from app.workspace.models import Artifact, ArtifactDependency, ArtifactVersion


def changed_fields(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = set()
        for key in before.keys() | after.keys():
            part = str(key).replace('~', '~0').replace('/', '~1')
            path = prefix + '/' + part
            if key not in before or key not in after:
                result.add(path)
            else:
                result.update(changed_fields(before[key], after[key], path))
        return result
    return set() if before == after else {prefix}


def _matches(edge_field, paths):
    return not edge_field or any(not path or path == edge_field or path.startswith(edge_field + '/') or edge_field.startswith(path + '/') for path in paths)


def affected_artifact_ids(db, workspace_id, artifact_id, paths):
    if not paths:
        return set()
    edges = db.query(ArtifactDependency).filter_by(workspace_id=workspace_id).all()
    affected = set()
    pending = [(artifact_id, paths)]
    while pending:
        upstream, changed = pending.pop()
        for edge in edges:
            if edge.upstream_id == upstream and edge.downstream_id != artifact_id and edge.downstream_id not in affected and _matches(edge.upstream_field, changed):
                affected.add(edge.downstream_id)
                pending.append((edge.downstream_id, {''}))
    return affected


def mark_affected(db, workspace_id, artifact_id, paths):
    affected = affected_artifact_ids(db, workspace_id, artifact_id, paths)
    if not affected:
        return
    rows = db.query(Artifact).filter(Artifact.workspace_id == workspace_id, Artifact.id.in_(affected)).all()
    blocked = set()
    for row in rows:
        version = db.query(ArtifactVersion).filter_by(artifact_id=row.id, version=row.version).first()
        if row.locked or row.review_status == 'approved' or (version and version.author_kind == 'teacher'):
            blocked.add(row.id)
    edges = db.query(ArtifactDependency).filter_by(workspace_id=workspace_id).all()
    while True:
        downstream = {edge.downstream_id for edge in edges if edge.upstream_id in blocked and edge.downstream_id in affected}
        if downstream <= blocked:
            break
        blocked.update(downstream)
    for row in rows:
        if row.id in blocked:
            row.review_status = 'needs_review'
        else:
            row.status = 'stale'
    db.flush()

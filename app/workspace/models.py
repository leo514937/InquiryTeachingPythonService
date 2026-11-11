from sqlalchemy import Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base


# Deliberately separate from the legacy metadata: disabled means no new tables.
WorkspaceBase = declarative_base()


class Workspace(WorkspaceBase):
    __tablename__ = 'workspace_workspaces'
    id = Column(String, primary_key=True)
    owner_user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    revision = Column(Integer, nullable=False, default=0)


class Artifact(WorkspaceBase):
    __tablename__ = 'workspace_artifacts'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    parent_id = Column(String, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default='active')
    locked = Column(Integer, nullable=False, default=0)
    review_status = Column(String, nullable=False, default='unreviewed')
    source_json = Column(Text, nullable=False, default='[]')
    change_paths_json = Column(Text, nullable=False, default='[]')
    version = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'type', 'parent_id'),)

    @property
    def content(self):
        import json
        return json.loads(self.content_json)


class ArtifactVersion(WorkspaceBase):
    __tablename__ = 'workspace_artifact_versions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)
    source_json = Column(Text, nullable=False, default='[]')
    author_kind = Column(String, nullable=False, default='teacher')
    run_id = Column(String, nullable=True)
    run_refs_json = Column(Text, nullable=False, default='[]')
    __table_args__ = (UniqueConstraint('artifact_id', 'version'),)


class RecordRequest(WorkspaceBase):
    __tablename__ = 'workspace_record_requests'
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String, nullable=False)
    experiment_id = Column(String, nullable=False)
    request_key = Column(String, nullable=False)
    artifact_id = Column(String, nullable=False)
    angle = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'experiment_id', 'request_key'),)


class ReportSnapshot(WorkspaceBase):
    __tablename__ = 'workspace_report_snapshots'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    content_json = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False)
    created_at = Column(String, nullable=False)


class WorkspaceRagAudit(WorkspaceBase):
    __tablename__ = 'workspace_rag_audits'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    run_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    expert_id = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    allowed_sources_json = Column(Text, nullable=False)
    hit_sources_json = Column(Text, nullable=False)
    chunk_ids_json = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(String, nullable=False)


class WorkspaceSetting(WorkspaceBase):
    __tablename__ = 'workspace_settings'
    key = Column(String, primary_key=True)
    value_json = Column(Text, nullable=False)


class WorkspaceRun(WorkspaceBase):
    __tablename__ = 'workspace_runs'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    owner_user_id = Column(String, nullable=False)
    request_key = Column(String, nullable=False)
    goal = Column(Text, nullable=False)
    mode = Column(String, nullable=False)
    input_revision = Column(Integer, nullable=False, default=0)
    replan_json = Column(Text, nullable=False, default='{}')
    context_json = Column(Text, nullable=False, default='{}', server_default='{}')
    status = Column(String, nullable=False, default='queued')
    plan_json = Column(Text, nullable=False, default='{}')
    error = Column(Text, nullable=False, default='')
    event_sequence = Column(Integer, nullable=False, default=0, server_default='0')
    cancel_requested = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String, nullable=True)
    lease_until = Column(String, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'request_key'),)


class WorkspaceActiveRun(WorkspaceBase):
    __tablename__ = 'workspace_active_runs'
    workspace_id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False, unique=True)


class WorkspaceNode(WorkspaceBase):
    __tablename__ = 'workspace_nodes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    node_id = Column(String, nullable=False)
    capability = Column(String, nullable=False)
    depends_json = Column(Text, nullable=False, default='[]')
    inputs_json = Column(Text, nullable=False, default='{}')
    output_json = Column(Text, nullable=False, default='{}')
    status = Column(String, nullable=False, default='queued')
    attempts = Column(Integer, nullable=False, default=0)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    changes_json = Column(Text, nullable=False, default='[]', server_default='[]')
    __table_args__ = (UniqueConstraint('run_id', 'node_id'),)


class WorkspaceEvent(WorkspaceBase):
    __tablename__ = 'workspace_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)
    data_json = Column(Text, nullable=False, default='{}')
    created_at = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint('run_id', 'sequence'),)


class ArtifactDependency(WorkspaceBase):
    __tablename__ = 'workspace_dependencies'
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String, nullable=False, index=True)
    upstream_id = Column(String, nullable=False)
    upstream_version = Column(Integer, nullable=False)
    upstream_field = Column(String, nullable=False, default='')
    downstream_id = Column(String, nullable=False)
    downstream_field = Column(String, nullable=False, default='')

import hashlib
import json
from app.workspace.artifacts.types import ACTIVITY_TYPES

from app.workspace.artifacts.service import _create_artifact, _id, _json, _now, _save_version
from app.workspace.models import Artifact, ArtifactVersion, ReportSnapshot, Workspace, WorkspaceRun
from sqlalchemy import update


def create_narrative(db, workspace_id, section_key, title, paragraphs):
    return _create_artifact(db, workspace_id, 'ReportNarrative', {
        'section_key': section_key, 'title': title, 'paragraphs': paragraphs, 'author_kind': 'teacher',
    })


def update_narrative(db, workspace_id, artifact_id, expected_version, paragraphs):
    row = db.query(Artifact).filter_by(id=artifact_id, workspace_id=workspace_id, type='ReportNarrative').first()
    if not row:
        raise LookupError('narrative not found')
    content = row.content
    content['paragraphs'] = paragraphs
    content['author_kind'] = 'teacher'
    return _save_version(db, row, expected_version, content)


def project_report(db, workspace_id):
    workspace = db.query(Workspace).filter_by(id=workspace_id).one()
    rows = db.query(Artifact).filter_by(workspace_id=workspace_id).all()
    section_order = {'teaching_context': 0, 'curriculum': 1, 'learning_goals': 2, 'inquiry_questions': 3,
                     'experiment': 4, 'records': 5, 'assessment': 6, 'notes': 7}
    def rank(row):
        if row.type == 'ReportNarrative':
            section = row.content.get('section_key', 'notes')
        else:
            section = 'experiment' if row.type in ACTIVITY_TYPES else {'KnowledgeCard': 'curriculum', 'LearningGoal': 'learning_goals', 'InquiryQuestion': 'inquiry_questions',
                       'Experiment': 'experiment', 'InquiryActivity': 'experiment', 'DataRecord': 'records', 'Assessment': 'assessment'}.get(row.type, 'notes')
        return (section_order.get(section, 7), row.order_index, row.id)
    rows.sort(key=rank)
    sections = []
    sources = []
    for row in rows:
        data = row.content
        if row.type == 'ReportNarrative':
            sections.append({'title': data['title'], 'paragraphs': data['paragraphs'], 'artifact_id': row.id, 'version': row.version})
            sources.extend(json.loads(row.source_json))
        elif row.type == 'Experiment':
            paragraphs = [str(data['description'])] if data.get('description') else []
            if data.get('component_type') == 'light_reflection_v1':
                paragraphs.append('理想平面镜模型')
            sections.append({'title': data.get('title', '实验'), 'paragraphs': paragraphs, 'artifact_id': row.id, 'version': row.version, 'student_instructions': str(data.get('student_instructions') or '')})
            sources.extend(json.loads(row.source_json))
        elif row.type in {'KnowledgeCard', 'LearningGoal', 'InquiryQuestion', 'Assessment'} | ACTIVITY_TYPES:
            title = str(data.get('title') or row.type)
            paragraphs = []
            for field in ('description', 'question', 'passages', 'questions', 'respondents', 'observation_targets', 'recording_method', 'data_sources', 'analysis_methods', 'roles', 'evidence_fields', 'presentation_formats', 'steps', 'materials', 'criteria'):
                value = data.get(field)
                if isinstance(value, str) and value.strip():
                    paragraphs.append(value)
                elif isinstance(value, list):
                    paragraphs.extend(str(item) for item in value if isinstance(item, (str, int, float)))
            sections.append({'title': title, 'paragraphs': paragraphs, 'artifact_id': row.id, 'version': row.version, 'student_instructions': str(data.get('student_instructions') or '')})
            sources.extend(json.loads(row.source_json))
        elif row.type == 'DataRecord' and data.get('include_in_report') is True:
            values = [f"入射角 {item['incident_angle_deg']}°，反射角 {item['reflected_angle_deg']}°" for item in data.get('records', [])]
            if data.get('conclusion'):
                values.append('观察结论：' + data['conclusion'])
            sections.append({'title': '实验记录与观察', 'paragraphs': values, 'artifact_id': row.id, 'version': row.version})
            sources.extend(json.loads(row.source_json))
    run = db.query(WorkspaceRun).filter_by(workspace_id=workspace_id).filter(WorkspaceRun.mode.in_(['lesson', 'experiment'])).order_by(WorkspaceRun.created_at.desc()).first()
    from app.workspace.context import TeachingContext
    teaching_context = TeachingContext.from_request(run.goal, json.loads(run.context_json or '{}')).model_dump(mode='json') if run else None
    return {'title': workspace.title, 'sections': sections, 'notice': '暂无可用课程标准依据' if not sources else '含课程标准参考，请核对原文', 'source_refs': sources, 'teaching_context': teaching_context}


def create_snapshot(db, workspace_id):
    # Acquire a workspace write lock so the projection sees one coherent set
    # of artifact versions even while a teacher or worker is editing.
    db.execute(update(Workspace).where(Workspace.id == workspace_id).values(revision=Workspace.revision))
    rows = db.query(Artifact).filter_by(workspace_id=workspace_id).all()
    for artifact in rows:
        version = db.query(ArtifactVersion).filter_by(artifact_id=artifact.id, version=artifact.version).first()
        if version:
            refs = json.loads(version.run_refs_json)
            if not isinstance(refs, list):
                raise ValueError('生成内容审核来源无效，无法导出')
            if version.run_id and version.run_id not in refs:
                refs.append(version.run_id)
            for run_id in refs:
                run = db.get(WorkspaceRun, run_id)
                if run is None or run.status != 'completed':
                    raise ValueError('包含未完成或待审核的生成内容，无法导出')
    data = project_report(db, workspace_id)
    payload = _json(data)
    snapshot = ReportSnapshot(id=_id('report'), workspace_id=workspace_id, content_json=payload,
                              content_hash=hashlib.sha256(payload.encode('utf-8')).hexdigest(), created_at=_now())
    db.add(snapshot)
    db.flush()
    return snapshot


def read_snapshot(db, workspace_id, snapshot_id):
    row = db.query(ReportSnapshot).filter_by(id=snapshot_id, workspace_id=workspace_id).first()
    if not row:
        raise LookupError('snapshot not found')
    return json.loads(row.content_json)

import importlib.util


def test_complete_lesson_requires_full_sections_and_projects_them():
    import pytest
    from app.workspace.lesson_bundle import validate_complete_lesson, make_artifacts
    payload = {'background': '学生经验待确认', 'situation': '建议调查使用次数', 'reflection': '检查数据口径',
               'goals': ['能统计'], 'questions': ['如何记录？'],
               'activities': [{'name': '调查', 'minutes': 40, 'goal_indexes': [0], 'teacher_preparation': '准备记录表',
                               'teacher_guide': '统一口径', 'student_task': '填写记录', 'evidence': '记录表',
                               'materials': ['纸'], 'safety': '保护隐私'}],
               'worksheet': {'steps': ['地点：____；次数：____次'], 'activity_indexes': [0]},
               'assessment': {'criteria': ['记录有单位'], 'goal_indexes': [0], 'activity_indexes': [0]},
               'resources': ['纸']}
    validate_complete_lesson(payload, 40)
    artifacts = make_artifacts(payload, 40)
    narratives = {a['content']['title']: a['content']['paragraphs'] for a in artifacts if a['type'] == 'ReportNarrative'}
    assert narratives['教学背景与学情'] == ['学生经验待确认']
    assert narratives['真实问题情境'] == ['建议调查使用次数']
    assert narratives['教学反思建议'] == ['检查数据口径']
    assert next(a for a in artifacts if a['type'] == 'InquiryActivity')['content']['teacher_preparation'] == '准备记录表'
    with pytest.raises(ValueError):
        validate_complete_lesson({k: v for k, v in payload.items() if k != 'reflection'}, 40)


def test_scene_catalog_and_rewrite_are_available():
    assert importlib.util.find_spec('app.workspace.scene_catalog') is not None
    from app.workspace.scene_catalog import load_scenes, rewrite_queries
    scenes = load_scenes()
    assert {'campus_life', 'science_lab', 'nature', 'local_culture', 'data_survey', 'custom'} <= set(scenes)
    items = rewrite_queries('设计校园垃圾分类课', {'grade': '四年级'}, ['campus_life'], ['curriculum', 'teaching_case'])
    assert len(items) == 2
    assert all('四年级' in item['query'] for item in items)
    assert all('source_ids' not in item for item in items)


def test_scene_catalog_route_is_registered():
    from app.workspace.api import scene_router
    assert any(route.path == '/api/inquiry-scenes' for route in scene_router.routes)


def test_scene_catalog_reports_configured_sources_without_claiming_authorization(monkeypatch):
    from types import SimpleNamespace
    import app.workspace.api as api
    import app.workspace.scene_catalog as catalog

    scenes = [catalog.Scene(id='empty', version=1, name='空场景', description='', intents=[], source_groups=['empty']),
              catalog.Scene(id='configured', version=1, name='有配置', description='', intents=[], source_groups=['group'])]
    monkeypatch.setattr(api, 'resolve_workspace_role', lambda *args: None)
    monkeypatch.setattr(catalog, 'load_scenes', lambda: {scene.id: scene for scene in scenes})
    monkeypatch.setattr(catalog, 'load_catalog', lambda: SimpleNamespace(source_groups={'empty': [], 'group': ['source-id']}))
    result = api.list_scenes(q='', db=None, user=None)['data']
    assert [scene['has_configured_sources'] for scene in result] == [False, True]
    assert result[1]['id'] == 'configured'


def test_diagnostics_route_requires_admin():
    from app.core.auth import get_admin_user
    from app.workspace.api import router
    route = next(route for route in router.routes if route.path.endswith('/diagnostics'))
    assert any(dependency.call is get_admin_user for dependency in route.dependant.dependencies)


def test_rule_rewrite_rejects_unknown_scene():
    import pytest
    from app.workspace.scene_catalog import rewrite_queries
    with pytest.raises(ValueError, match='invalid scenes'):
        rewrite_queries('主题', {}, ['unknown'], ['curriculum'])


def test_scene_conflicts_are_rejected(monkeypatch):
    import pytest
    import app.workspace.scene_catalog as catalog
    scenes = {'a': catalog.Scene(id='a', version=1, name='A', description='', intents=[], incompatible_with=['b']),
              'b': catalog.Scene(id='b', version=1, name='B', description='', intents=[])}
    monkeypatch.setattr(catalog, 'load_scenes', lambda: scenes)
    with pytest.raises(ValueError, match='冲突'):
        catalog.rewrite_queries('主题', {}, ['a', 'b'], ['curriculum'])


def test_empty_catalog_returns_explicit_no_sources_without_search():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.workspace.models import WorkspaceBase
    from app.workspace.enrichment import build_scene_context
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        result = build_scene_context(db, '课题', {'scene_ids': ['campus_life']}, 'ws', 'run', 'teacher')
        assert result['status'] == 'no_sources'
        assert result['curriculum_evidence'] == []
        assert result['environment_facts'] == []


def test_custom_source_without_permission_is_not_silently_treated_as_empty():
    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.workspace.models import WorkspaceBase
    from app.workspace.enrichment import build_scene_context
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        with pytest.raises(PermissionError):
            build_scene_context(db, '课题', {'scene_ids': ['custom'], 'custom_source_ids': ['not-authorized']}, 'ws', 'run', 'teacher')


def test_lesson_quality_rejects_activity_time_mismatch():
    import pytest
    from app.workspace.lesson_bundle import validate_lesson
    payload = {'goals': ['能提出问题'], 'questions': ['为什么？'],
               'activities': [{'name': '观察', 'minutes': 20, 'goal_indexes': [0], 'teacher_guide': '提问', 'student_task': '观察', 'evidence': '记录', 'materials': ['纸'], 'safety': '教师确认'}],
               'worksheet': {'steps': ['记录'], 'activity_indexes': [0]},
               'assessment': {'criteria': ['能记录'], 'goal_indexes': [0], 'activity_indexes': [0]},
               'resources': ['纸']}
    with pytest.raises(ValueError, match='课时'):
        validate_lesson(payload, 40)


def test_lesson_quality_rejects_dangling_goal_reference():
    import pytest
    from app.workspace.lesson_bundle import validate_lesson
    payload = {'goals': ['能提出问题'], 'questions': ['为什么？'],
               'activities': [{'name': '观察', 'minutes': 40, 'goal_indexes': [1], 'teacher_guide': '提问', 'student_task': '观察', 'evidence': '记录', 'materials': ['纸'], 'safety': '教师确认'}],
               'worksheet': {'steps': ['记录'], 'activity_indexes': [0]},
               'assessment': {'criteria': ['能记录'], 'goal_indexes': [0], 'activity_indexes': [0]},
               'resources': ['纸']}
    with pytest.raises(ValueError, match='引用'):
        validate_lesson(payload, 40)


def test_scene_run_input_rejects_invalid_scene_id():
    import pytest
    from app.workspace.context import TeachingContext
    with pytest.raises(ValueError):
        TeachingContext.model_validate({'studio_mode': True, 'scene_ids': ['invalid']})


def test_nested_studio_mode_cannot_run_as_experiment():
    import pytest
    from app.workspace.api import RunInput
    with pytest.raises(ValueError, match='仅支持'):
        RunInput.model_validate({'goal': '课题', 'idempotency_key': 'one', 'mode': 'experiment',
                                 'teaching_context': {'studio_mode': True}})


def test_quality_creates_server_owned_artifact_references():
    from app.workspace.lesson_bundle import make_artifacts
    payload = {'goals': ['能提出问题'], 'questions': ['为什么？'],
               'activities': [{'name': '观察', 'minutes': 40, 'goal_indexes': [0], 'teacher_guide': '提问', 'student_task': '观察', 'evidence': '记录', 'materials': ['纸'], 'safety': '教师确认'}],
               'worksheet': {'steps': ['记录'], 'activity_indexes': [0]},
               'assessment': {'criteria': ['能记录'], 'goal_indexes': [0], 'activity_indexes': [0]}, 'resources': ['纸']}
    artifacts = make_artifacts(payload, 40)
    ids = {a['type']: a['server_id'] for a in artifacts}
    activity = next(a for a in artifacts if a['type'] == 'InquiryActivity')
    assessment = next(a for a in artifacts if a['type'] == 'Assessment')
    assert activity['content']['goal_ids'] == [ids['LearningGoal']]
    assert assessment['content']['goal_ids'] == [ids['LearningGoal']]
    assert assessment['content']['activity_ids'] == [ids['InquiryActivity']]


def test_studio_capabilities_are_registered_and_empty_sources_fall_back():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.workspace.models import WorkspaceBase
    from app.workspace.capabilities.builtin import build_registry
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    registry = build_registry(None, sessionmaker(bind=engine))
    for cap in ('context.enrich@1', 'lesson.bundle@1', 'quality.rules@1'):
        assert registry.get(cap).version == 1
    output = registry.invoke('context.enrich@1', {'workspace_id': 'ws', 'run_id': 'r', 'user_id': 'u'},
                             {'goal': '探究', 'teaching_context': {'scene_ids': [], 'allow_without_evidence': False}})
    assert output['scene_context']['status'] == 'no_sources'
    assert output['sources'] == []
    assert '未引用已核实课程依据' in output['warnings']


def test_no_retrieval_hits_fall_back_without_inventing_sources(monkeypatch):
    from contextlib import nullcontext
    from app.workspace.capabilities.builtin import build_registry
    import app.workspace.enrichment as enrichment
    pack = {'status': 'no_results', 'evidence_refs': [], 'missing_information': ['未检索到可用知识依据']}
    monkeypatch.setattr(enrichment, 'build_scene_context', lambda *args: pack)
    class Sessions:
        def begin(self):
            return nullcontext(None)
    output = build_registry(None, Sessions()).invoke(
        'context.enrich@1', {'workspace_id': 'ws', 'run_id': 'r', 'user_id': 'u'},
        {'goal': '探究', 'teaching_context': {}})
    assert output['scene_context']['status'] == 'no_results'
    assert output['sources'] == []
    assert '未引用已核实课程依据' in output['warnings']


def test_studio_profile_is_a_validated_three_stage_plan():
    from app.workspace.orchestrator.planner import studio_plan, validate_plan
    plan = studio_plan('四年级探究')
    assert [node.capability for node in plan.nodes] == ['context.enrich@1', 'lesson.bundle@1', 'quality.rules@1']
    assert validate_plan(plan.model_dump()) == plan
    assert plan.nodes[2].depends_on == ['bundle']


def test_studio_run_uses_runtime_and_persists_only_validated_artifacts(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.workspace.models import WorkspaceBase, WorkspaceRun, Artifact
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "studio.db").as_posix()}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        ws = create_workspace(db, 'teacher', '探究课')
        run = create_run(db, ws.id, 'teacher', '四年级探究课40分钟', 'lesson', 'key',
                         {'studio_mode': True, 'scene_ids': ['campus_life']})
        run_id, ws_id = run.id, ws.id
    class FakeModel:
        def complete(self, system, message):
            return json.dumps({'background': '学情待确认', 'situation': '建议观察', 'reflection': '检查记录', 'goals': ['能观察'], 'questions': ['有什么变化？'],
                               'activities': [{'name': '观察', 'minutes': 40, 'goal_indexes': [0], 'teacher_preparation': '准备纸', 'teacher_guide': '指导观察',
                                               'student_task': '记录', 'evidence': '记录表', 'materials': ['纸'], 'safety': '教师确认'}],
                               'worksheet': {'steps': ['画出发现'], 'activity_indexes': [0]},
                               'assessment': {'criteria': ['能记录'], 'goal_indexes': [0], 'activity_indexes': [0]}, 'resources': ['纸']}, ensure_ascii=False)
    execute_builtin_run(factory, run_id, FakeModel(), authorize=lambda db, user: None)
    with factory() as db:
        assert db.get(WorkspaceRun, run_id).status == 'completed'
        rows = db.query(Artifact).filter_by(workspace_id=ws_id).all()
        assert {'LearningGoal', 'InquiryQuestion', 'InquiryActivity', 'StudentWorksheet', 'Assessment', 'ResourceChecklist'} <= {a.type for a in rows}
        assert all(a.content for a in rows)
        from app.workspace.reports.service import project_report
        sections = project_report(db, ws_id)['sections']
        titles = [section['title'] for section in sections]
        assert titles.index('教学背景与学情') < titles.index('教学目标 1') < titles.index('真实问题情境')
        assert titles.index('真实问题情境') < titles.index('探究问题 1') < titles.index('观察')
        assert titles.index('观察') < titles.index('学生任务单') < titles.index('学习评价') < titles.index('教学反思建议')
        assert '教师准备：准备纸' in next(section for section in sections if section['title'] == '观察')['paragraphs']
    engine.dispose()


def test_strategy_configuration_selects_without_granting_permissions():
    from app.workspace.teaching_strategy import select_strategy
    science = select_strategy('科学')
    assert science['id'] == 'science_inquiry'
    assert select_strategy('未知')['id'] == 'general_inquiry'
    assert 'source_ids' not in science


def test_no_evidence_error_has_explicit_safe_code():
    from app.workspace.enrichment import NoEvidence
    from app.workspace.runtime.runs import _safe_error_code
    assert _safe_error_code(NoEvidence('暂无可用知识依据')) == 'no_evidence'


def test_report_projects_worksheet_and_resource_artifacts():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase
    from app.workspace.artifacts.service import create_workspace, _create_artifact
    from app.workspace.reports.service import project_report
    engine = create_engine('sqlite:///:memory:')
    WorkspaceBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        ws = create_workspace(db, 'teacher', '课')
        _create_artifact(db, ws.id, 'StudentWorksheet', {'title': '任务单', 'steps': ['画种子']})
        _create_artifact(db, ws.id, 'ResourceChecklist', {'title': '材料', 'materials': ['纸']})
        report = project_report(db, ws.id)
        assert [section['title'] for section in report['sections']] == ['任务单', '材料']


def test_source_version_change_blocks_prior_evidence():
    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.db.models import CurriculumSourceModel, CurriculumSourceAgentPermissionModel
    from app.workspace.models import WorkspaceBase, WorkspaceSetting
    from app.workspace.integrations.rag import assert_sources_authorized
    import json
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine); WorkspaceBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(CurriculumSourceModel(source='test.md', id='test-id', category='curriculum', title='test', checksum='new', updated_at='now'))
        db.add(CurriculumSourceAgentPermissionModel(source='test.md', agent_id='expert', role_category='teacher', created_at='now'))
        db.add(WorkspaceSetting(key='allowed_experts', value_json=json.dumps(['expert'])))
        db.commit()
        with pytest.raises(HTTPException):
            assert_sources_authorized(db, [{'source': 'test.md', 'expert_id': 'expert', 'source_version': 'old'}])


def test_isolated_authorized_source_is_retrieved_and_audited(tmp_path, monkeypatch):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    from app.db.database import Base
    from app.db.models import CurriculumSourceModel, CurriculumSourceAgentPermissionModel
    from app.services.curriculum_knowledge_service import CurriculumKnowledgeService
    from app.workspace.models import WorkspaceBase, WorkspaceSetting, WorkspaceRagAudit
    from app.workspace.enrichment import build_scene_context
    engine = create_engine(f'sqlite:///{(tmp_path / "rag.db").as_posix()}')
    Base.metadata.create_all(engine); WorkspaceBase.metadata.create_all(engine)
    settings = get_settings()
    monkeypatch.setattr(settings, 'curriculum_vector_enabled', False)
    monkeypatch.setattr(settings, 'curriculum_rag_enabled', True)
    with sessionmaker(bind=engine)() as db:
        CurriculumKnowledgeService(db, settings).ingest('fixture.md', '校园垃圾分类探究活动，观察与记录。', category='curriculum')
        source = db.get(CurriculumSourceModel, 'fixture.md')
        db.add(CurriculumSourceAgentPermissionModel(source=source.source, agent_id='expert', role_category='teacher', created_at='now'))
        db.add(WorkspaceSetting(key='allowed_experts', value_json=json.dumps(['expert'])))
        db.commit()
        result = build_scene_context(db, '校园垃圾分类', {'scene_ids': ['custom'], 'custom_source_ids': [source.id]}, 'ws', 'run', 'teacher')
        assert result['status'] == 'retrieved'
        assert result['evidence_refs'][0]['source_id'] == source.id
        assert db.query(WorkspaceRagAudit).count() > 0


def test_studio_profile_configuration_is_schema_validated():
    from app.workspace.profile import load_profile
    profile = load_profile('minimal_lesson')
    assert [node['capability'] for node in profile['nodes']] == ['context.enrich@1', 'lesson.bundle@1', 'quality.rules@1']


def test_studio_generated_artifacts_record_goal_and_activity_dependencies(tmp_path):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from app.workspace.models import WorkspaceBase, Artifact, ArtifactDependency
    from app.workspace.artifacts.service import create_workspace
    from app.workspace.runtime.runs import create_run, execute_builtin_run
    engine = create_engine(f'sqlite:///{(tmp_path / "deps.db").as_posix()}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine); WorkspaceBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        ws = create_workspace(db, 'teacher', '课')
        run_id = create_run(db, ws.id, 'teacher', '40分钟', 'lesson', 'key', {'studio_mode': True, 'allow_without_evidence': True}).id
        workspace_id = ws.id
    class FakeModel:
        def complete(self, *_):
            return json.dumps({'background':'学情待确认', 'situation':'建议观察', 'reflection':'检查记录', 'goals':['观察'], 'questions':['什么'], 'activities':[{'name':'观察','minutes':40,'goal_indexes':[0], 'teacher_preparation':'准备纸', 'teacher_guide':'引导','student_task':'记录','evidence':'记录','materials':['纸'],'safety':'确认'}], 'worksheet':{'steps':['记录'],'activity_indexes':[0]}, 'assessment':{'criteria':['记录'],'goal_indexes':[0],'activity_indexes':[0]}, 'resources':['纸']}, ensure_ascii=False)
    execute_builtin_run(factory, run_id, FakeModel(), authorize=lambda db, user: None)
    with factory() as db:
        rows = {x.type:x for x in db.query(Artifact).filter_by(workspace_id=workspace_id)}
        edges = {(x.upstream_id,x.downstream_id) for x in db.query(ArtifactDependency).filter_by(workspace_id=workspace_id)}
        assert (rows['LearningGoal'].id, rows['InquiryActivity'].id) in edges
        assert (rows['InquiryActivity'].id, rows['Assessment'].id) in edges
        assert (rows['InquiryActivity'].id, rows['StudentWorksheet'].id) in edges
    engine.dispose()


def test_report_rejects_stale_studio_artifact_until_reviewed():
    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.workspace.models import WorkspaceBase
    from app.workspace.artifacts.service import create_workspace, _create_artifact, confirm_artifact_review
    from app.workspace.runtime.runs import create_run
    from app.workspace.reports.service import create_snapshot
    engine = create_engine('sqlite:///:memory:'); WorkspaceBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        ws = create_workspace(db, 'teacher', '课')
        run = create_run(db, ws.id, 'teacher', '课', 'lesson', 'key', {'studio_mode': True})
        run.status = 'completed'
        artifact = _create_artifact(db, ws.id, 'StudentWorksheet', {'title': '任务单', 'steps': ['记录']}, author_kind='agent', run_id=run.id)
        artifact.status = 'stale'; db.flush()
        with pytest.raises(ValueError, match='检查'):
            create_snapshot(db, ws.id)
        confirmed = confirm_artifact_review(db, ws.id, artifact.id, artifact.version)
        assert confirmed.status == 'active' and confirmed.version == 2
        assert create_snapshot(db, ws.id).id

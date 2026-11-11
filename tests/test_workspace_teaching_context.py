import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.workspace.models import WorkspaceBase, WorkspaceRun
from app.workspace.artifacts.service import create_workspace
from app.workspace.runtime.runs import create_run
from app.workspace.context import TeachingContext


def test_context_preserves_explicit_inputs_and_marks_unknowns():
    context = TeachingContext.from_request('如何调查班级图书角', {'subject':'数学','grade':'五年级','resources':['图书'], 'duration_minutes':40})
    assert context.subject == '数学' and context.grade == '五年级'
    assert context.resources == ['图书'] and context.duration_minutes == 40
    assert '阅读与语言水平未提供' in context.assumptions
    assert context.topic == '如何调查班级图书角'
    assert '光的反射' not in context.model_dump_json()


def test_run_persists_context_and_idempotency_covers_it():
    engine=create_engine('sqlite://')
    WorkspaceBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory.begin() as db:
        workspace=create_workspace(db,'teacher','校园图书角')
        run=create_run(db,workspace.id,'teacher','调查图书角','lesson','key',{'grade':'五年级','subject':'数学'})
        assert json.loads(run.context_json)['grade']=='五年级'
        assert create_run(db,workspace.id,'teacher','调查图书角','lesson','key',{'grade':'五年级','subject':'数学'}).id==run.id
        with pytest.raises(ValueError,match='idempotency'):
            create_run(db,workspace.id,'teacher','调查图书角','lesson','key',{'grade':'三年级','subject':'数学'})
    engine.dispose()

def test_same_context_reaches_planner_and_capability_without_fabricating_grade():
    from app.workspace.orchestrator.planner import plan_goal
    from app.workspace.capabilities.builtin import build_registry
    class Model:
        def __init__(self): self.messages=[]
        def complete(self, system, message):
            self.messages.append((system,message))
            if '规划器' in system:
                return json.dumps({'version':1,'goal':'调查图书角','nodes':[{'id':'q','capability':'inquiry.design@1','depends_on':[],'inputs':{}}]})
            return json.dumps({'summary':'观察文本','artifacts':[{'type':'InquiryQuestion','content':{'title':'如何分类','question':'你怎样分类？'}}],'warnings':[]},ensure_ascii=False)
    model=Model()
    context=TeachingContext.from_request('调查图书角',{'subject':'数学','grade':'五年级'}).model_dump(mode='json')
    plan_goal(model,'调查图书角',teaching_context=context)
    build_registry(model).invoke('inquiry.design@1',{}, {'goal':'调查图书角','parameters':{},'dependencies':{},'teaching_context':context})
    assert all('五年级' in message and '数学' in message for _,message in model.messages)
    assert all('光的反射' not in message for _,message in model.messages)

def test_context_migration_keeps_old_runs_and_is_idempotent():
    from sqlalchemy import inspect, text
    from app.workspace.migrations import ensure_workspace_schema
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE workspace_runs (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, request_key TEXT NOT NULL, goal TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, plan_json TEXT NOT NULL, error TEXT NOT NULL, cancel_requested INTEGER NOT NULL, lease_owner TEXT, lease_until TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO workspace_runs VALUES ('r','w','u','k','旧主题','lesson','completed','{}','',0,NULL,NULL,'now','now')"))
    ensure_workspace_schema(engine);ensure_workspace_schema(engine)
    assert 'context_json' in {column['name'] for column in inspect(engine).get_columns('workspace_runs')}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT goal,context_json FROM workspace_runs WHERE id='r'")).one()==('旧主题','{}')
    engine.dispose()

def test_explicit_grade_and_duration_in_teacher_request_are_shared_without_guessing():
    context=TeachingContext.from_request('小学四年级语文人物描写，40分钟',{})
    assert context.grade=='四年级'
    assert context.stage=='小学'
    assert context.duration_minutes==40
    assert '年级未提供' not in context.assumptions
    assert TeachingContext.from_request('探究植物',{}).grade==''
    assert TeachingContext.from_request('小学四年级，40分钟',{'grade':'五年级'}).grade=='五年级'

def test_learner_profile_differentiates_grade_bands_and_marks_guidance():
    lower=TeachingContext.from_request('课程',{'grade':'一年级','stage':'小学'}).learner_profile
    middle=TeachingContext.from_request('课程',{'grade':'四年级','stage':'小学'}).learner_profile
    upper=TeachingContext.from_request('课程',{'grade':'六年级','stage':'小学'}).learner_profile
    assert lower and middle and upper
    assert len({lower.language_guidance,middle.language_guidance,upper.language_guidance})==3
    assert len({lower.task_guidance,middle.task_guidance,upper.task_guidance})==3
    assert lower.teacher_support != upper.teacher_support
    assert lower.is_recommendation is True
    assert TeachingContext.from_request('年级未知的课程',{}).learner_profile is None

def test_explicit_subject_is_captured_but_mixed_disciplines_are_not_guessed():
    assert TeachingContext.from_request('小学四年级语文：人物描写',{}).subject=='语文'
    assert TeachingContext.from_request('在数学和语文课中比较表达',{}).subject==''
    assert TeachingContext.from_request('小学语文人物描写',{'subject':'综合实践'}).subject=='综合实践'

def test_ambiguous_stage_does_not_create_a_primary_school_profile():
    assert TeachingContext.from_request('课程',{'grade':'一年级'}).learner_profile is None
    assert TeachingContext.from_request('课程',{'grade':'一年级','stage':'小学'}).learner_profile is not None
    assert TeachingContext.from_request('课程',{'grade':'一年级','stage':'高中'}).learner_profile is None

def test_context_rejects_unbounded_list_items():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TeachingContext.from_request('课程',{'resources':['x'*2001]})

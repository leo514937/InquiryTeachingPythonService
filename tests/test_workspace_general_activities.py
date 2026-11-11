import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.workspace.models import WorkspaceBase
from app.workspace.artifacts.service import create_workspace, _create_artifact
from app.workspace.capabilities.builtin import build_registry
from app.workspace.reports.service import project_report


def test_language_inquiry_can_generate_a_reading_task_without_reflection():
    class Model:
        def complete(self, system, message):
            return json.dumps({'summary':'阅读比较','artifacts':[{'type':'ReadingInquiryTask','content':{'title':'比较语言描写','description':'比较两处描写','student_instructions':'圈出描写动作的词。'}}], 'warnings':[]},ensure_ascii=False)
    result=build_registry(Model()).invoke('activity.design@1',{}, {'goal':'四年级语文人物描写','parameters':{},'dependencies':{}})
    assert result['artifacts'][0]['type']=='ReadingInquiryTask'
    assert '光的反射' not in json.dumps(result,ensure_ascii=False)


def test_report_includes_generic_activity_and_student_language():
    engine=create_engine('sqlite://');WorkspaceBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory.begin() as db:
        ws=create_workspace(db,'teacher','人物描写')
        item=_create_artifact(db,ws.id,'ReadingInquiryTask',{'title':'比较描写','description':'观察人物语言','student_instructions':'圈出关键词'})
        report=project_report(db,ws.id)
        section=next(section for section in report['sections'] if section['artifact_id']==item.id)
        assert section['title']=='比较描写'
        assert '圈出关键词' in section['student_instructions']
        assert section['version']==1
        assert '光的反射' not in json.dumps(report,ensure_ascii=False)
    engine.dispose()

def test_report_discloses_missing_context_instead_of_inventing_it():
    from app.workspace.runtime.runs import create_run
    engine=create_engine('sqlite://');WorkspaceBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory.begin() as db:
        ws=create_workspace(db,'teacher','人物描写')
        create_run(db,ws.id,'teacher','人物描写','lesson','context',{'subject':'语文','grade':'四年级'})
        report=project_report(db,ws.id)
        assert report['teaching_context']['subject']=='语文'
        assert '阅读与语言水平未提供' in report['teaching_context']['assumptions']
    engine.dispose()

def test_specialist_activity_capabilities_are_registered_and_plannable():
    from app.workspace.orchestrator.planner import validate_plan
    expected={'reading.design@1':'ReadingInquiryTask','survey.design@1':'SurveyTask','data.design@1':'DataInquiryTask'}
    class Model:
        def __init__(self, kind): self.kind=kind
        def complete(self, system, message):
            return json.dumps({'summary':'活动','artifacts':[{'type':self.kind,'content':{'title':'任务','description':'探究','student_instructions':'记录发现'}}],'warnings':[]},ensure_ascii=False)
    for capability,kind in expected.items():
        plan=validate_plan({'version':1,'goal':'课堂探究','nodes':[{'id':'a','capability':capability,'depends_on':[],'inputs':{}}]})
        assert plan.nodes[0].capability==capability
        result=build_registry(Model(kind)).invoke(capability,{}, {'goal':'课堂探究','parameters':{},'dependencies':{}})
        assert result['artifacts'][0]['type']==kind

def test_planner_rejects_unknown_component_before_execution():
    from app.workspace.orchestrator.planner import validate_plan
    import pytest
    bad={'version':1,'goal':'图书分类','nodes':[{'id':'c','capability':'component.bind@1','depends_on':[],'inputs':{'component_type':'lesson_plan'}}]}
    with pytest.raises(ValueError,match='component'):
        validate_plan(bad)

def test_specialist_activity_rejects_missing_student_instructions():
    import pytest
    from app.workspace.capabilities.builtin import ModelOutputInvalid
    class Model:
        def complete(self, system, message):
            return json.dumps({'summary':'阅读','artifacts':[{'type':'ReadingInquiryTask','content':{'title':'任务','description':'阅读'}}],'warnings':[]},ensure_ascii=False)
    with pytest.raises(ModelOutputInvalid):
        build_registry(Model()).invoke('reading.design@1',{}, {'goal':'阅读','parameters':{},'dependencies':{}})

def test_report_keeps_survey_questions_as_teaching_evidence_plan():
    engine=create_engine('sqlite://');WorkspaceBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory.begin() as db:
        ws=create_workspace(db,'teacher','图书调查')
        _create_artifact(db,ws.id,'SurveyTask',{'title':'调查同学','description':'了解借阅','questions':['你希望增加哪类书？'],'student_instructions':'礼貌地询问一位同学。'})
        report=project_report(db,ws.id)
        assert any('你希望增加哪类书？' in text for section in report['sections'] for text in section['paragraphs'])
    engine.dispose()

def test_unselected_optional_component_does_not_default_to_reflection():
    result=build_registry(None).invoke('component.bind@1',{}, {'goal':'人物描写','parameters':{},'dependencies':{}})
    assert 'light_reflection' not in result['summary']
    chosen=build_registry(None).invoke('component.bind@1',{}, {'goal':'光的反射','parameters':{'component_type':'light_reflection_v1'},'dependencies':{}})
    assert 'light_reflection_v1' in chosen['summary']

def test_specialist_capability_contract_exposes_scope_and_version():
    registry=build_registry(None)
    reading=registry.get('reading.design@1')
    assert reading.version==1
    assert reading.applicability and '文本' in reading.applicability
    assert reading.permission=='teacher' and reading.timeout_seconds>0
    assert reading.side_effects is False
    assert registry.get('knowledge.retrieve@1').side_effects is True

def test_invalid_planning_has_specific_safe_error_category():
    from app.workspace.orchestrator.planner import PlanValidationError
    from app.workspace.runtime.runs import _safe_error_code
    assert _safe_error_code(PlanValidationError('invalid'))=='plan_invalid'

def test_lesson_plan_retries_when_activity_cannot_access_goal_ids():
    from app.workspace.orchestrator.planner import plan_goal
    class Model:
        calls=0
        def complete(self, system, message):
            self.calls+=1
            dependencies=[] if self.calls==1 else ['goal']
            return json.dumps({'version':1,'goal':'种植观察','nodes':[{'id':'goal','capability':'goals.compose@1','depends_on':[],'inputs':{}},{'id':'activity','capability':'activity.design@1','depends_on':dependencies,'inputs':{}},{'id':'question','capability':'inquiry.design@1','depends_on':[],'inputs':{}},{'id':'assessment','capability':'assessment.design@1','depends_on':['goal'],'inputs':{}}]},ensure_ascii=False)
    model=Model()
    plan=plan_goal(model,'种植观察',mode='lesson')
    assert model.calls==2
    assert plan.nodes[1].depends_on==['goal']

def test_activity_retries_hallucinated_goal_references_when_goal_is_available():
    class Model:
        calls=0
        def complete(self, system, message):
            self.calls+=1
            goal='invented' if self.calls==1 else 'real-goal'
            return json.dumps({'summary':'完成','artifacts':[{'type':'ReadingInquiryTask','content':{'title':'阅读','description':'比较','student_instructions':'圈出句子','goal_ids':[goal]}}],'warnings':[]},ensure_ascii=False)
    model=Model()
    deps={'goal':{'artifacts':[{'type':'LearningGoal','content':{'title':'目标'}}], 'artifact_refs':[{'id':'real-goal','version':1}], 'sources':[]}}
    result=build_registry(model).invoke('reading.design@1',{}, {'goal':'语文阅读','parameters':{},'dependencies':deps})
    assert model.calls==2
    assert result['artifacts'][0]['content']['goal_ids']==['real-goal']

def test_complete_lesson_repairs_missing_inquiry_before_execution():
    from app.workspace.orchestrator.planner import plan_goal
    class Model:
        calls=0
        def complete(self, system, message):
            self.calls+=1
            nodes=[{'id':'goal','capability':'goals.compose@1','depends_on':[],'inputs':{}},
                   {'id':'activity','capability':'activity.design@1','depends_on':['goal'],'inputs':{}},
                   {'id':'assessment','capability':'assessment.design@1','depends_on':['goal'],'inputs':{}}]
            if self.calls>1:
                nodes.append({'id':'question','capability':'inquiry.design@1','depends_on':[],'inputs':{}})
            return json.dumps({'version':1,'goal':'植物探究','nodes':nodes},ensure_ascii=False)
    model=Model();plan=plan_goal(model,'植物探究',mode='lesson')
    assert model.calls==2
    assert any(node.capability=='inquiry.design@1' for node in plan.nodes)

def test_planner_repair_feedback_explains_disconnected_curriculum_in_chinese():
    from app.workspace.orchestrator.planner import plan_goal
    class Model:
        calls=0
        def complete(self, system, message):
            self.calls+=1
            if self.calls==2:
                assert '课程依据检索' in message and '直接依赖' in message
            rag=[] if self.calls==1 else [{'id':'rag','capability':'knowledge.retrieve@1','depends_on':[],'inputs':{}}]
            nodes=rag+[{'id':'goal','capability':'goals.compose@1','depends_on':['rag'] if rag else [],'inputs':{}}, {'id':'question','capability':'inquiry.design@1','depends_on':[],'inputs':{}}, {'id':'activity','capability':'activity.design@1','depends_on':['goal'],'inputs':{}}, {'id':'assessment','capability':'assessment.design@1','depends_on':['goal'],'inputs':{}}]
            return json.dumps({'version':1,'goal':'植物探究','nodes':nodes},ensure_ascii=False)
    model=Model();plan_goal(model,'植物探究',mode='lesson',allowed_experts=['physics_teacher_agent'])
    assert model.calls==2

def test_planner_has_bounded_repair_for_multiple_distinct_plan_errors():
    from app.workspace.orchestrator.planner import plan_goal
    class Model:
        calls=0
        def complete(self, system, message):
            self.calls+=1
            goal_dep=[] if self.calls<3 else ['goal']
            nodes=[{'id':'goal','capability':'goals.compose@1','depends_on':[],'inputs':{}}, {'id':'activity','capability':'activity.design@1','depends_on':goal_dep,'inputs':{}}, {'id':'assessment','capability':'assessment.design@1','depends_on':['goal'],'inputs':{}}]
            if self.calls>1:
                nodes.append({'id':'question','capability':'inquiry.design@1','depends_on':[],'inputs':{}})
            return json.dumps({'version':1,'goal':'植物探究','nodes':nodes},ensure_ascii=False)
    model=Model();plan=plan_goal(model,'植物探究',mode='lesson')
    assert model.calls==3
    assert any(node.capability=='inquiry.design@1' for node in plan.nodes)

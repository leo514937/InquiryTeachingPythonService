"""Isolated browser-test service; never imported by the application."""
import json
import os
import sys
import time
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
real_model = os.getenv('INQUIRY_E2E_REAL_MODEL') == '1'
temp = tempfile.TemporaryDirectory(prefix='inquiry-browser-test-', ignore_cleanup_errors=True)
test_dir = Path(temp.name)
os.environ.update({
    'DATABASE_URL': f"sqlite:///{(test_dir / 'test.db').as_posix()}",
    'INQUIRY_WORKSPACE_ENABLED': 'true',
    'UPLOAD_DIR': str(test_dir / 'uploads'),
    'KNOWLEDGE_SOURCE_DIR': str(test_dir / 'sources'),
    'CURRICULUM_VECTOR_ENABLED': 'false',
    'ECOLOGY_GRAPH_AUTO_SYNC_ENABLED': 'false',
    'GLOBI_IMPORT_WORKER_ENABLED': 'false',
    'FRONTEND_ORIGIN': 'http://127.0.0.1:' + os.getenv('INQUIRY_E2E_WEB_PORT', '15730'),
    **({} if real_model else {'LLM_API_KEY': 'browser-test'}),
})

from app.main import app
from app.db.database import SessionLocal
from app.db.models import CurriculumSourceModel, CurriculumSourceAgentPermissionModel
from app.services.rag_service import RagService
from app.workspace.integrations.rag import set_allowed_experts
from app.workspace.integrations.llm import StrictLLM


with SessionLocal.begin() as db:
    if real_model:
        from app.services.curriculum_knowledge_service import CurriculumKnowledgeService
        CurriculumKnowledgeService(db).ingest('test-standard.md', ('学生应通过观察、阅读、调查、记录和讨论收集证据，并根据年级特点进行安全探究与表达。' if os.getenv('INQUIRY_E2E_GENERAL') == '1' else '实验验证光的反射规律：反射角等于入射角。学生应通过安全观察、记录、比较数据解释实验现象。'), category='curriculum')
    else:
        db.add(CurriculumSourceModel(source='test-standard.md', category='curriculum', updated_at='now'))
    db.flush()
    db.add(CurriculumSourceAgentPermissionModel(source='test-standard.md', agent_id='physics_teacher_agent', role_category='teacher', created_at='now'))
    set_allowed_experts(db, ['physics_teacher_agent'])


def retrieval(db, **kwargs):
    if kwargs['allowed_sources'] != ['test-standard.md']:
        raise ValueError('unexpected retrieval scope')
    return '反射现象课程参考', {'mode': 'local_bm25', 'hit_sources': ['test-standard.md'], 'records': [{'source': 'test-standard.md', 'chunk_id': 1}]}


def node(id, capability, depends=(), inputs=None):
    return {'id': id, 'capability': capability, 'depends_on': list(depends), 'inputs': inputs or {}}


def completion(self, system, message):
    if '慢速图' in message and '规划器' not in system:
        time.sleep(0.6)
    if '规划器' in system and '局部上下文：' in message:
        context = json.loads(message.split('局部上下文：', 1)[1].split('\n上次计划', 1)[0])
        capabilities = {'LearningGoal':'goals.compose@1', 'InquiryQuestion':'inquiry.design@1', 'Experiment':'activity.design@1', 'InquiryActivity':'activity.design@1', 'Assessment':'assessment.design@1', 'KnowledgeCard':'knowledge.map@1', 'ReportNarrative':'report.narrative@1'}
        ids = {item['id']: f'target_{i}' for i, item in enumerate(context['targets'])}
        nodes = [node(ids[item['id']], capabilities[item['type']], [ids[edge['upstream_id']] for edge in context['edges'] if edge['downstream_id'] == item['id']], {'target_artifact_id':item['id']}) for item in context['targets']]
        nodes.append(node('quality', 'quality.evaluate@1', list(ids.values())))
        return json.dumps({'version':1, 'goal':'局部调整', 'nodes':nodes}, ensure_ascii=False)
    if '规划器' in system and '教学上下文：' in message:
        context = json.loads(message.split('教学上下文：', 1)[1].split('\n局部上下文：', 1)[0].split('\n上次计划', 1)[0])
        subject = context.get('subject')
        if not subject and '反射' not in context.get('topic', ''):
            subject = '综合'
        if subject in ('科学', '语文', '数学', '跨学科', '综合'):
            capability = {'科学':'activity.design@1', '语文':'reading.design@1', '数学':'data.design@1', '跨学科':'survey.design@1', '综合':'activity.design@1'}[subject]
            nodes = [node('rag','knowledge.retrieve@1',inputs={'expert_id':'physics_teacher_agent'}), node('goal','goals.compose@1',['rag']), node('question','inquiry.design@1',['goal']), node('activity',capability,['goal','question']), node('assessment','assessment.design@1',['goal','activity']), node('quality','quality.evaluate@1',['goal','question','activity','assessment'])]
            return json.dumps({'version':1,'goal':context.get('topic') or '课堂探究','nodes':nodes},ensure_ascii=False)
    if '规划器' in system:
        nodes = [node('rag', 'knowledge.retrieve@1', inputs={'expert_id': 'physics_teacher_agent'}),
                 node('goal', 'goals.compose@1', ['rag']), node('question', 'inquiry.design@1', ['goal']),
                 node('activity', 'activity.design@1', ['goal', 'question']),
                 node('assessment', 'assessment.design@1', ['goal', 'activity']),
                 node('quality', 'quality.evaluate@1', ['goal', 'question', 'activity', 'assessment'])]
        return json.dumps({'version': 1, 'goal': '光的反射', 'nodes': nodes}, ensure_ascii=False)
    capability = next(name for name in ('goals.compose@1', 'inquiry.design@1', 'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1', 'assessment.design@1', 'quality.evaluate@1') if name in system)
    data = json.loads(message)
    if data.get('parameters', {}).get('target_artifact_id'):
        context = json.loads(data['dependencies']['_workspace_context']['summary'])
        target = next(item for item in context['targets'] if item['id'] == data['parameters']['target_artifact_id'])
        content = {**target['content'], 'title': '更新后' + target['content'].get('title', target['type'])}
        return json.dumps({'summary':'局部更新', 'artifacts':[{'type':target['type'], 'content':content}], 'warnings':[]}, ensure_ascii=False)
    task_context = data.get('teaching_context', {})
    subject = task_context.get('subject')
    if not subject and '反射' not in task_context.get('topic', ''):
        subject = '综合'
    if subject in ('科学', '语文', '数学', '跨学科', '综合'):
        goal_ids = [item['id'] for item in data['dependencies'].get('goal', {}).get('artifact_refs', [])]
        activity = {'科学':('ObservationTask','观察植物与阳光'), '语文':('ReadingInquiryTask','比较人物语言'), '数学':('DataInquiryTask','整理图书分类数据'), '跨学科':('SurveyTask','安全观察校园交通'), '综合':('InquiryActivity','探究活动')}[subject]
        artifacts = {'goals.compose@1':[{'type':'LearningGoal','content':{'title':'学习目标','description':'基于证据解释问题'}}], 'inquiry.design@1':[{'type':'InquiryQuestion','content':{'title':'探究问题','question':'我们如何收集证据？'}}], 'assessment.design@1':[{'type':'Assessment','content':{'title':'学习评价','criteria':['解释所获证据'],'goal_ids':goal_ids}}], 'quality.evaluate@1':[]}
        if capability in ('activity.design@1','reading.design@1','survey.design@1','data.design@1'):
            artifacts[capability]=[{'type':activity[0], 'content':{'title':activity[1], 'description':'观察并交流发现', 'student_instructions':'记录你发现的证据。', 'goal_ids':goal_ids}}]
        return json.dumps({'summary':'完成','artifacts':artifacts[capability],'warnings':[]},ensure_ascii=False)
    goal_ids = [item['id'] for item in data['dependencies'].get('goal', {}).get('artifact_refs', [])]
    artifacts = {
        'goals.compose@1': [{'type': 'LearningGoal', 'content': {'title': '理解反射规律', 'description': '比较入射角和反射角'}}],
        'inquiry.design@1': [{'type': 'InquiryQuestion', 'content': {'title': '探究问题', 'question': '两角有什么关系？'}}],
        'activity.design@1': [{'type': 'Experiment', 'content': {'title': '光的反射实验', 'description': '观察光线', 'materials': ['镜子'], 'safety_measures': ['成人监督'], 'component_type': 'light_reflection_v1'}}, {'type': 'InquiryActivity', 'content': {'title': '记录数据', 'description': '比较角度', 'goal_ids': goal_ids}}],
        'assessment.design@1': [{'type': 'Assessment', 'content': {'title': '形成性评价', 'criteria': ['比较角度'], 'goal_ids': goal_ids}}],
        'quality.evaluate@1': [],
    }[capability]
    if '审核图' in data.get('goal', '') and capability == 'activity.design@1':
        artifacts[0]['content']['materials'].append('激光笔')
    return json.dumps({'summary': '完成', 'artifacts': artifacts, 'warnings': []}, ensure_ascii=False)


if real_model and os.getenv('INQUIRY_E2E_DIAGNOSTICS') == '1':
    from app.workspace.runtime import runs as runtime_runs
    original_error_code = runtime_runs._safe_error_code
    def diagnostic_error_code(exc):
        code = original_error_code(exc)
        cause = exc.__cause__
        reason = 'none'
        if cause is not None:
            from pydantic import ValidationError
            if isinstance(cause, ValidationError):
                reason = ','.join(sorted({str(item.get('type', 'unknown')) for item in cause.errors(include_input=False)}))
            elif isinstance(cause, json.JSONDecodeError):
                reason = 'json_decode'
            else:
                text = str(cause)
                known = ('unknown component', 'unknown capability', 'duplicate node id', 'duplicate dependency', 'missing dependency', 'cycle in plan', 'plan too deep', 'curriculum retrieval is missing or disconnected', 'activity and assessment nodes require direct goal dependencies', 'complete lesson requires goal, inquiry question, activity and assessment capabilities')
                reason = next((item for item in known if item in text), 'other')
        message = f"category={code}; exception={type(exc).__name__}; cause={type(cause).__name__ if cause else 'none'}; reason={reason}"
        print('isolated runtime failure:', message, flush=True)
        diagnostic_file = os.getenv('INQUIRY_E2E_DIAGNOSTICS_FILE')
        if diagnostic_file:
            with open(diagnostic_file, 'a', encoding='utf-8') as stream:
                stream.write(message + '\n')
        return code
    runtime_runs._safe_error_code = diagnostic_error_code

if not real_model:
    RagService.retrieve_curriculum_context = staticmethod(retrieval)
    StrictLLM.complete = completion

if __name__ == '__main__':
    import uvicorn
    try:
        uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('INQUIRY_E2E_PORT', '18760')), log_level='warning')
    finally:
        from app.db.database import engine
        engine.dispose()
        temp.cleanup()

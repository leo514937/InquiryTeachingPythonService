"""Constrained capability implementations for teaching artifacts."""
import json

from pydantic import BaseModel, ConfigDict, Field

from app.workspace.capabilities.registry import Capability, CapabilityRegistry
from app.workspace.artifacts.types import ACTIVITY_TYPES
from app.workspace.artifacts.components import is_known_component


class ModelOutputInvalid(ValueError):
    """Model output could not be validated after bounded correction."""


class CapabilityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str = Field(min_length=1, max_length=4000)
    parameters: dict = Field(default_factory=dict)
    dependencies: dict = Field(default_factory=dict)
    teaching_context: dict = Field(default_factory=dict)


class ArtifactOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: str
    content: dict


class SpecialistActivityContent(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=10000)
    student_instructions: str = Field(min_length=1, max_length=10000)
    goal_ids: list[str] = Field(default_factory=list, max_length=50)


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(max_length=10000)
    artifacts: list[ArtifactOutput] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=30)


class CapabilityOutput(ModelOutput):
    sources: list[dict[str, str]] = Field(default_factory=list)


_ALLOWED = {
    'requirements.analyze@1': set(),
    'knowledge.map@1': {'KnowledgeCard'},
    'goals.compose@1': {'LearningGoal', 'KnowledgeCard'},
    'inquiry.design@1': {'InquiryQuestion'},
    'activity.design@1': set(ACTIVITY_TYPES),
    'reading.design@1': {'ReadingInquiryTask'},
    'survey.design@1': {'SurveyTask', 'ObservationTask'},
    'data.design@1': {'DataInquiryTask'},
    'assessment.design@1': {'Assessment'},
    'quality.evaluate@1': set(),
    'report.narrative@1': {'ReportNarrative'},
}

_REQUIRED_OUTPUT = {
    'goals.compose@1': {'LearningGoal'},
    'inquiry.design@1': {'InquiryQuestion'},
    'activity.design@1': set(ACTIVITY_TYPES),
    'reading.design@1': {'ReadingInquiryTask'},
    'survey.design@1': {'SurveyTask', 'ObservationTask'},
    'data.design@1': {'DataInquiryTask'},
    'assessment.design@1': {'Assessment'},
}


CAPABILITY_IDS = frozenset({*_ALLOWED, 'knowledge.retrieve@1', 'report.assemble@1', 'component.bind@1'})
_SPECIALIST_GUIDANCE = {
    'reading.design@1': '设计适龄文本观察、比较与证据解释，学生任务使用适合年级的语言。',
    'survey.design@1': '设计与真实环境相关的观察或调查，说明对象、记录方法、隐私与安全限制。',
    'data.design@1': '设计适龄分类、记录、统计、比较和基于数据的解释活动。',
}


def _inherited_sources(dependencies):
    result = {}
    for value in dependencies.values():
        if not isinstance(value, dict):
            raise ValueError('invalid dependency')
        for source in value.get('sources', []):
            if not isinstance(source, dict) or not isinstance(source.get('expert_id'), str) or not isinstance(source.get('source'), str):
                raise ValueError('invalid source')
            result[(source['expert_id'], source['source'])] = {'expert_id': source['expert_id'], 'source': source['source']}
    return list(result.values())


def build_registry(model, session_factory=None):
    registry = CapabilityRegistry()
    for capability_id, permitted in _ALLOWED.items():
        def handler(context, data, capability_id=capability_id, permitted=permitted):
            prompt = (
                f'你正在执行教学原子能力 {capability_id}。只返回一个 JSON 对象：'
                '{"summary":"摘要","artifacts":[{"type":"类型","content":{}}],"warnings":[]}。'
                f'允许的教学对象 type（区分大小写）：{", ".join(sorted(permitted)) or "无"}。'
                + ('本能力不创建教学对象，必须返回 "artifacts":[]；分析或检查结果写入 summary。'
                   if not permitted else
                   '仅可使用列出的类型，不能将中文名称、其他类型或通用教案作为对象 type。')
                + ('本能力必须在 artifacts 中至少返回一个以下类型的教学对象：'
                   + ', '.join(sorted(_REQUIRED_OUTPUT[capability_id])) + '。'
                   if capability_id in _REQUIRED_OUTPUT else '')
                + _SPECIALIST_GUIDANCE.get(capability_id, '')
                + '不得虚构课程标准；不确定安全性时写入 warnings。不要附加与主题无关的专用交互组件。'
                '根据统一教学上下文中的年级、语言水平、资源与安全要求设计活动；未提供的条件不得当成事实。'
                '教师说明使用专业教学语言；如果提供学生任务语言，应符合该年级阅读能力，且不能虚构课堂表现。'
                '对象 content 使用 title、description；问题可以使用 question，步骤、材料及评价标准可以使用 steps、materials、criteria 数组。'
                '实验应提供 materials、description 和 safety_measures；阅读、观察、调查、数据和表达任务应使用对应类型。'
                '学生任务指令放在 student_instructions 字段，教师说明放在 description 字段。'
                'InquiryActivity 和 Assessment 的 goal_ids 应只引用依赖结果中真实存在的 LearningGoal ID；不得编造 ID。'
                'ReportNarrative 必须包含 section_key、title、paragraphs 字段。'
            )
            message = data.model_dump_json()
            goal_ids = set()
            for dependency in data.dependencies.values():
                if not isinstance(dependency, dict):
                    continue
                for item, ref in zip(dependency.get('artifacts', []), dependency.get('artifact_refs', [])):
                    if isinstance(item, dict) and item.get('type') == 'LearningGoal' and isinstance(ref, dict) and isinstance(ref.get('id'), str):
                        goal_ids.add(ref['id'])
            payload = None
            for attempt in range(2):
                try:
                    payload = ModelOutput.model_validate(json.loads(model.complete(prompt, message)))
                    for artifact in payload.artifacts:
                        if artifact.type not in permitted:
                            raise ValueError('unexpected artifact type')
                        if capability_id in _SPECIALIST_GUIDANCE:
                            SpecialistActivityContent.model_validate(artifact.content)
                        if goal_ids and artifact.type in (ACTIVITY_TYPES - {'Experiment', 'EvidenceRecord'}) | {'Assessment'}:
                            refs = artifact.content.get('goal_ids')
                            if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs) or set(refs) != goal_ids:
                                raise ValueError('activity must reference the real goal ids from dependencies')
                        if artifact.type == 'Experiment' and not is_known_component(artifact.content.get('component_type')):
                            raise ValueError('unknown component')
                        if not isinstance(artifact.content.get('title'), str) or not artifact.content['title'].strip():
                            raise ValueError('artifact title is required')
                        if artifact.type == 'ReportNarrative' and (not isinstance(artifact.content.get('section_key'), str) or not isinstance(artifact.content.get('paragraphs'), list) or not all(isinstance(p, str) for p in artifact.content['paragraphs'])):
                            raise ValueError('invalid report narrative')
                    required = _REQUIRED_OUTPUT.get(capability_id)
                    if required and not any(artifact.type in required for artifact in payload.artifacts):
                        raise ValueError('required artifact missing')
                    break
                except (ValueError, TypeError) as exc:
                    if attempt:
                        if str(exc) == 'unknown component':
                            raise ValueError('unsupported component') from None
                        raise ModelOutputInvalid('模型输出未通过能力校验，请重试') from None
                    message = (data.model_dump_json() + '\\n上次输出未通过校验。请严格按指定 JSON 格式、允许的类型及必需的 artifacts 重新输出；'
                               '禁止输出未允许的类型。若依赖中有学习目标，活动和评价的 goal_ids 必须完整引用依赖返回的真实目标 ID，禁止编造；阅读、调查和数据任务须包含 title、description 和非空 student_instructions 字段；若本能力不创建对象，artifacts 必须为空数组。')
            return {**payload.model_dump(), 'sources': _inherited_sources(data.dependencies)}
        registry.register(Capability(capability_id, CapabilityInput, CapabilityOutput, handler, applicability=_SPECIALIST_GUIDANCE.get(capability_id, '按教学目标选择的通用教学能力')))

    def retrieve(context, data):
        if session_factory is None:
            raise ValueError('retrieval session unavailable')
        from app.workspace.integrations.rag import get_allowed_experts, retrieve_authorized
        with session_factory.begin() as db:
            configured = get_allowed_experts(db)
            expert = data.parameters.get('expert_id') or (configured[0] if configured else '')
            query = str(data.parameters.get('query') or data.goal)[:4000]
            text, info = retrieve_authorized(db, workspace_id=context['workspace_id'], run_id=context['run_id'],
                                             user_id=context['user_id'], expert_id=expert,
                                             configured_experts=configured, query=query)
            sources = [{'expert_id': expert, 'source': source} for source in info.get('hit_sources', [])]
            return {'summary': text, 'artifacts': [], 'warnings': [] if sources else ['暂无可用课程标准依据'], 'sources': sources}
    registry.register(Capability('knowledge.retrieve@1', CapabilityInput, CapabilityOutput, retrieve, side_effects=True, applicability='授权课程资料检索，记录检索审计', idempotency='每次检索可能新增审计记录，成果提交由运行时控制'))

    def assemble(context, data):
        return {'summary': '报告由教学对象投影生成', 'artifacts': [], 'warnings': [], 'sources': _inherited_sources(data.dependencies)}
    registry.register(Capability('report.assemble@1', CapabilityInput, CapabilityOutput, assemble))

    def bind(context, data):
        component_id = data.parameters.get('component_type')
        if not is_known_component(component_id):
            raise ValueError('unknown component')
        summary = f'交互组件可用：{component_id}' if component_id else '未选择专用交互组件，使用通用活动展示'
        return {'summary': summary, 'artifacts': [], 'warnings': [], 'sources': _inherited_sources(data.dependencies)}
    registry.register(Capability('component.bind@1', CapabilityInput, CapabilityOutput, bind))
    return registry

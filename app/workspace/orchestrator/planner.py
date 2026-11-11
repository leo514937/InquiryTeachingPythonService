from typing import Literal
import json

from pydantic import BaseModel, ConfigDict, Field


# Planning and runtime share the built-in capability catalog.
from app.workspace.capabilities.builtin import CAPABILITY_IDS
from app.workspace.artifacts.components import is_known_component


class PlanValidationError(ValueError):
    """Planner output could not be validated after bounded correction."""


class PlanNode(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    capability: str
    depends_on: list[str]
    inputs: dict


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1]
    goal: str = Field(min_length=1, max_length=4000)
    nodes: list[PlanNode] = Field(min_length=1, max_length=30)


def studio_plan(goal: str) -> Plan:
    """A server-owned minimal profile; teachers never choose capability IDs."""
    from app.workspace.profile import load_profile
    return validate_plan({'version': 1, 'goal': goal, 'nodes': load_profile('minimal_lesson')['nodes']})


def validate_plan(payload):
    plan = Plan.model_validate(payload)
    nodes = {node.id: node for node in plan.nodes}
    if len(nodes) != len(plan.nodes):
        raise ValueError('duplicate node id')
    for node in plan.nodes:
        if node.capability not in CAPABILITY_IDS:
            raise ValueError('unknown capability')
        if node.capability == 'component.bind@1' and not is_known_component(node.inputs.get('component_type')):
            raise ValueError('unknown component')
        if len(node.depends_on) != len(set(node.depends_on)):
            raise ValueError('duplicate dependency')
        if any(dependency not in nodes for dependency in node.depends_on):
            raise ValueError('missing dependency')
    visiting, depths = set(), {}
    def depth(node_id):
        if node_id in visiting:
            raise ValueError('cycle in plan')
        if node_id in depths:
            return depths[node_id]
        visiting.add(node_id)
        result = 1 + max((depth(dep) for dep in nodes[node_id].depends_on), default=0)
        visiting.remove(node_id)
        if result > 12:
            raise ValueError('plan too deep')
        depths[node_id] = result
        return result
    for node_id in nodes:
        depth(node_id)
    return plan


def plan_goal(model, goal, *, mode=None, allowed_experts=None, replan_context=None, validate_context=None, teaching_context=None):
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 4000:
        raise ValueError('invalid goal')
    prompt = (
        '你是教学任务规划器。根据需求选择必要的原子能力和依赖，不使用固定阶段模板。'
        '只返回 JSON，包含 version=1、goal、nodes。每个节点包含 id、capability、depends_on 和 inputs。'
        '不得使用未列出的能力；依赖必须是节点 ID；最多 30 个节点。'
        '各节点 inputs 是能力参数，依赖节点输出会自动传给下游。'
        '仅在教学主题与交互组件匹配时选择 component.bind@1；目前可选组件仅 light_reflection_v1，否则不要绑定组件。'
        '教学设计须包含目标、问题、活动与评价；独立实验应生成实验。'
        '根据上下文的学科、年级与资源选择观察、阅读、调查、数据分析或实验等适用活动；不要套用固定模板。'
        'reading.design@1 用于文本阅读探究，survey.design@1 用于调查与观察，data.design@1 用于数据分析；activity.design@1 用于其他活动或实验。'
        '只选择本任务实际需要的专业能力，不要为了覆盖能力而加入无关的阅读、调查、数据或实验节点，也不要让不同节点重复生成同一活动。'
        '完整教学方案中若包含目标生成节点，活动与评价节点须将目标生成节点列为直接依赖，以便取得真实目标 ID。'
        '为低年级降低阅读负担、缩短任务并增加教师支持；高年级逐步提高证据分析和合作自主性。'
        '缺失的信息应明确标注未提供，禁止当作事实猜测。' 
        '已有课标专家时，必须创建 knowledge.retrieve@1 课程依据检索节点，并让目标或其他内容生成节点在 depends_on 中直接依赖它；不得把检索节点孤立或放在生成节点之后。可用能力：'
        + ', '.join(sorted(CAPABILITY_IDS))
    )
    if allowed_experts:
        prompt += '。可用教师专家 ID：' + ', '.join(allowed_experts)
    prompt += '。本次任务类型：' + (mode or '自动判断')
    if replan_context is not None:
        prompt += '。局部修改时，每个需要生成教学对象的节点必须在 inputs.target_artifact_id 填写一个指定目标 ID，不得生成其他对象。'
    context_text = json.dumps(replan_context, ensure_ascii=False) if replan_context is not None else ''
    if len(context_text) > 24000:
        raise ValueError('replan context is too large')
    error = None
    for attempt in range(3 if mode in ('lesson', 'experiment') else 2):
        try:
            message = goal + ('\n教学上下文：' + json.dumps(teaching_context, ensure_ascii=False) if teaching_context else '') + ('\n局部上下文：' + context_text if context_text else '')
            if attempt:
                reason = str(error)[:500]
                hints = {
                    'curriculum retrieval is missing or disconnected': '请创建课程依据检索节点，并让目标或其他内容生成节点直接依赖该检索节点。',
                    'activity and assessment nodes require direct goal dependencies': '请让每个活动和评价节点直接依赖所有目标生成节点。',
                    'complete lesson requires goal, inquiry question, activity and assessment capabilities': '请补齐目标、探究问题、活动和评价所需能力。',
                    'unknown component': '只可选择已注册且与任务相符的交互组件；没有合适组件时不要绑定。',
                }
                message += '\n上次计划未通过验证：' + reason + '。' + hints.get(reason, '') + '请返回修正后的完整 JSON。'
            payload = json.loads(model.complete(prompt, message))
            plan = validate_plan(payload)
            if mode == 'lesson':
                goal_nodes = {n.id for n in plan.nodes if n.capability == 'goals.compose@1'}
                activity_caps = {'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1', 'assessment.design@1'}
                if goal_nodes and any(not goal_nodes.issubset(set(n.depends_on)) for n in plan.nodes if n.capability in activity_caps):
                    raise ValueError('activity and assessment nodes require direct goal dependencies')
            if mode == 'lesson' and allowed_experts:
                retrieval_ids = {n.id for n in plan.nodes if n.capability == 'knowledge.retrieve@1'}
                downstream = {n.id for n in plan.nodes if n.capability in {'goals.compose@1', 'inquiry.design@1', 'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1', 'assessment.design@1', 'report.narrative@1'}}
                reachable = set(retrieval_ids)
                for _ in plan.nodes:
                    reachable.update(n.id for n in plan.nodes if any(dep in reachable for dep in n.depends_on))
                if not retrieval_ids or not (downstream & reachable):
                    raise ValueError('curriculum retrieval is missing or disconnected')
            if mode == 'lesson':
                capabilities = {node.capability for node in plan.nodes}
                required = {'goals.compose@1', 'inquiry.design@1', 'assessment.design@1'}
                activity_caps = {'activity.design@1', 'reading.design@1', 'survey.design@1', 'data.design@1'}
                if not required.issubset(capabilities) or not (capabilities & activity_caps):
                    raise ValueError('complete lesson requires goal, inquiry question, activity and assessment capabilities')
            if validate_context:
                validate_context(plan)
            return plan
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            error = exc
    raise PlanValidationError('模型返回的计划未通过验证') from error

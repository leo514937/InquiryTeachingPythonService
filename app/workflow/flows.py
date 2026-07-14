from copy import deepcopy
from typing import Any


FLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "inquiry_7_stage": {
        "name": "inquiry_7_stage",
        "display_name": "七阶段科学探究流",
        "description": "从观察起点到延伸新问题，完整支撑探究式科学课设计。",
        "stages": [
            {
                "id": "observation_start",
                "name": "观察起点",
                "expert": "情境探寻专家",
                "agent_id": "stage_observation_start",
                "direction": "引导教师描述本课题从什么现象、生活事件或具体实物开始，建立学生的直观兴趣。",
            },
            {
                "id": "question_refine",
                "name": "循疑问题",
                "expert": "问题提炼导师",
                "agent_id": "stage_question_refine",
                "direction": "帮助老师把孩子们直观、零散的发问提炼为有探究价值的主问题。",
            },
            {
                "id": "hypothesis",
                "name": "可能的猜想",
                "expert": "头脑风暴教练",
                "agent_id": "stage_hypothesis",
                "direction": "容纳孩子们的猜想，并将其归纳为可验证的科学假设。",
            },
            {
                "id": "experiment_design",
                "name": "实验设计",
                "expert": "实验设计专家",
                "agent_id": "stage_experiment_design",
                "direction": "指导教师设计对比实验，理清自变量、因变量与控制变量，做好安全规程。",
            },
            {
                "id": "new_questions",
                "name": "实验中的新问题",
                "expert": "教育契机捕手",
                "agent_id": "stage_new_questions",
                "direction": "预测实验中可能出现的异常操作或现象偏差，转化为生成性探究契机。",
            },
            {
                "id": "conclusion",
                "name": "可能的结论",
                "expert": "证据链整理师",
                "agent_id": "stage_conclusion",
                "direction": "引导教师教会孩子们通过实证证据进行阶段性推理，避免直接灌输结论。",
            },
            {
                "id": "extension",
                "name": "延伸与新问题",
                "expert": "探究闭环架构师",
                "agent_id": "stage_extension",
                "direction": "总结本轮探究，将未解现象或引申思考作为下一轮探究的起点。",
            },
        ],
    },
    "three_step_inquiry": {
        "name": "three_step_inquiry",
        "display_name": "三步快速探究流",
        "description": "适合短课时或快速备课：观察起点、问题提出、科学探究。",
        "stages": [
            {
                "id": "observe",
                "name": "观察起点",
                "expert": "情境探寻专家",
                "agent_id": "stage_observation_start",
                "direction": "快速构建真实情境，让学生产生可追问的现象困惑。",
            },
            {
                "id": "ask",
                "name": "问题提出",
                "expert": "问题提炼导师",
                "agent_id": "stage_question_refine",
                "direction": "把学生发问聚焦为可验证、可操作、可评价的核心探究问题。",
            },
            {
                "id": "investigate",
                "name": "科学探究",
                "expert": "实验设计专家",
                "agent_id": "stage_experiment_design",
                "direction": "组织实验、证据记录、结论表达与课堂评价。",
            },
        ],
    },
    "steam_project": {
        "name": "steam_project",
        "display_name": "STEAM 项目化探究流",
        "description": "面向跨学科项目制课堂，强调原型制作、证据迭代和成果展示。",
        "stages": [
            {
                "id": "scenario",
                "name": "真实情境",
                "expert": "项目情境设计师",
                "agent_id": "stage_observation_start",
                "direction": "把科学概念嵌入真实任务或生活挑战，形成项目驱动力。",
            },
            {
                "id": "challenge",
                "name": "工程挑战",
                "expert": "挑战定义导师",
                "agent_id": "stage_question_refine",
                "direction": "把任务边界、材料限制、评价标准讲清楚。",
            },
            {
                "id": "prototype",
                "name": "原型制作",
                "expert": "原型迭代教练",
                "agent_id": "stage_experiment_design",
                "direction": "指导学生设计、测试、记录和迭代原型。",
            },
            {
                "id": "showcase",
                "name": "展示评价",
                "expert": "学习评价设计师",
                "agent_id": "stage_extension",
                "direction": "帮助教师设计展示、互评、证据归纳和迁移反思。",
            },
        ],
    },
}


def list_flows() -> list[dict[str, Any]]:
    return [
        {
            "name": flow["name"],
            "display_name": flow["display_name"],
            "description": flow["description"],
            "stage_count": len(flow["stages"]),
            "stages": deepcopy(flow["stages"]),
        }
        for flow in FLOW_TEMPLATES.values()
    ]


def get_flow(flow_name: str) -> dict[str, Any]:
    if flow_name not in FLOW_TEMPLATES:
        raise KeyError(f"Unknown flow: {flow_name}")
    return deepcopy(FLOW_TEMPLATES[flow_name])


def get_stage(flow_name: str, index: int) -> dict[str, Any]:
    flow = get_flow(flow_name)
    stages = flow["stages"]
    if index < 0 or index >= len(stages):
        raise IndexError(f"Stage index out of range: {index}")
    return deepcopy(stages[index])

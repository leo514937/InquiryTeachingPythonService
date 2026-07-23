from copy import deepcopy
from typing import Any


STAGE_DIRECTIONS: dict[str, str] = {
    "observation_start": (
        "你要帮助教师完成情境创设与观察起步。\n"
        "1. 围绕学生可接触的真实现象或可模拟情境，先设计一个能激起好奇心的“认知诱饵”，让问题先被看见。\n"
        "2. 可以优先考虑失衡装置、异常对比、结果反常、明显缺口等素材，让学生意识到“这里有不对劲的地方”。\n"
        "3. 观察引导要植入“摹略思维”，即把观察变成有结构的记录，而不是随意浏览。\n"
        "4. 可配套观察任务单，明确学生要看什么、记什么、比什么，重点关注边界在哪里、什么在变化、什么保持不变。"
    ),
    "question_refine": (
        "你要帮助教师把零散发问提炼为有价值的核心问题，并先画清系统边界。\n"
        "1. 先梳理系统要素关系图，明确哪些是系统内变量、哪些是外部干扰、哪些是待验证对象。\n"
        "2. 用“小故 / 大故”来推进问题提炼：先找“缺少哪个条件就必然失败”的必要条件，再找“哪些条件同时具备就更可能成功”的充分条件。\n"
        "3. 引导学生把模糊提问改写成可探究、可验证、可操作的主问题，而不是停留在经验判断。\n"
        "4. 在表达上保持聚焦，帮助学生从“想到什么问什么”走向“围绕系统边界问为什么”。"
    ),
    "hypothesis": (
        "你要帮助教师把学生的猜想整理成多个可比较、可证伪的假设，并保留探索张力。\n"
        "1. 鼓励学生先发散，尽量提出不同解释路径，不急于过早收敛到唯一答案。\n"
        "2. 结合系统探索学习法，从系统、变量、关系、证据四个角度看待猜想，避免只凭直觉下结论。\n"
        "3. 借用墨家思维中的“察类明故”，引导学生区分现象判断、原因判断和机制判断，让猜想更接近可检验的命题。\n"
        "4. 可顺带比较哪些假设更容易被观察和测试，哪些假设虽然合理但暂时证据不足，以便后续进入实验设计。"
    ),
    "experiment_design": (
        "你要帮助教师把猜想落成低成本、可操作、可复现的测试方案。\n"
        "1. 优先明确测试目标、变量设置、对照条件、记录方式和安全边界，让学生知道“改什么、看什么、记什么”。\n"
        "2. 可以引导学生制作简单原型或小规模验证装置，用最小成本把关键变量显性化。\n"
        "3. 融入“研取思维”，强调真正的知识来自真实情境中的取舍与判断：证据支持哪个方案，为什么排除其他方案。\n"
        "4. 提前布防“试错”和“遇疑”，提醒学生把意外结果当作有价值的线索，并继续追问它为什么会发生。"
    ),
    "new_questions": (
        "你要帮助教师把测试中的异常结果、偏差和意外发现转化为新的探究机会。\n"
        "1. 重点不是立刻修正结果，而是先记录异常、对照现象、追踪原因，弄清它为什么和预期不同。\n"
        "2. 鼓励学生从“逢疑、循疑、遇疑、过疑”四个角度审视测试过程：哪里被表象带偏，哪里依赖了经验，哪里出现了意外，哪里推理跳步了。\n"
        "3. 用系统探索学习法把偏差重新放回系统中看，判断是变量设置问题、操作问题、测量问题还是原理问题。\n"
        "4. 把异常提炼成新的问题，帮助教师把一次测试延伸成下一轮探究的入口。"
    ),
    "conclusion": (
        "你要帮助教师把测试得到的证据整理成阶段性结论，并避免结论跳跃。\n"
        "1. 先把观察事实、实验数据、推理过程、阶段结论分开表达，确保学生知道自己是凭什么得出判断的。\n"
        "2. 用“小故 / 大故”回看证据链：哪些条件是结论成立的必要条件，哪些条件组合起来更接近充分条件。\n"
        "3. 借鉴墨家“以验定说”的态度，鼓励学生用证据说话，而不是用声音大小或经验权威定输赢。\n"
        "4. 结论要保留边界和条件，明确“在什么情况下成立、还缺什么证据、哪些地方仍然待验证”。"
    ),
    "extension": (
        "你要帮助教师完成总结、迁移与下一轮探究起点的设计。\n"
        "1. 先回看本轮形成的问题、证据、结论和遗留疑问，梳理出一条清晰的探究闭环。\n"
        "2. 把未解现象或可迁移情境转化为新的认知诱饵，让学生看到知识可以继续生长。\n"
        "3. 引导学生思考：同一原理还能在哪里用，条件改变后结论是否变化，哪些判断需要重新测试。\n"
        "4. 让教师把本轮经验沉淀成可复用的方法，而不是只停留在单次课堂结果。"
    ),
}


STAGE_DISPLAY_DIRECTIONS: dict[str, str] = {
    "observation_start": "从真实现象或模拟情境切入，设计能激发好奇的观察起点。",
    "question_refine": "围绕系统边界和小故/大故，把零散发问提炼成可探究的核心问题。",
    "hypothesis": "鼓励多路径猜想，整理成可比较、可证伪的假设。",
    "experiment_design": "把猜想落成低成本测试方案，明确变量、对照、记录与安全边界。",
    "new_questions": "把异常结果和偏差转化为新的探究机会，继续追问。",
    "conclusion": "基于证据整理阶段性结论，强调条件、边界与可验证性。",
    "extension": "总结探究闭环，迁移到新情境并生成下一轮问题。",
}


def stage_item(
    *,
    id: str,
    name: str,
    expert: str,
    agent_id: str,
    direction_key: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "expert": expert,
        "agent_id": agent_id,
        "direction": STAGE_DIRECTIONS[direction_key],
        "display_direction": STAGE_DISPLAY_DIRECTIONS[direction_key],
    }


FLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "inquiry_7_stage": {
        "name": "inquiry_7_stage",
        "display_name": "七阶段科学探究流",
        "description": "从观察起点到延伸新问题，完整支撑探究式科学课设计。",
        "stages": [
            stage_item(
                id="observation_start",
                name="观察起点",
                expert="情境探寻专家",
                agent_id="stage_observation_start",
                direction_key="observation_start",
            ),
            stage_item(
                id="question_refine",
                name="循疑问题",
                expert="问题提炼导师",
                agent_id="stage_question_refine",
                direction_key="question_refine",
            ),
            stage_item(
                id="hypothesis",
                name="可能的猜想",
                expert="头脑风暴教练",
                agent_id="stage_hypothesis",
                direction_key="hypothesis",
            ),
            stage_item(
                id="experiment_design",
                name="实验设计",
                expert="实验设计专家",
                agent_id="stage_experiment_design",
                direction_key="experiment_design",
            ),
            stage_item(
                id="new_questions",
                name="实验中的新问题",
                expert="教育契机捕手",
                agent_id="stage_new_questions",
                direction_key="new_questions",
            ),
            stage_item(
                id="conclusion",
                name="可能的结论",
                expert="证据链整理师",
                agent_id="stage_conclusion",
                direction_key="conclusion",
            ),
            stage_item(
                id="extension",
                name="延伸与新问题",
                expert="探究闭环架构师",
                agent_id="stage_extension",
                direction_key="extension",
            ),
        ],
    },
    "three_step_inquiry": {
        "name": "three_step_inquiry",
        "display_name": "三步快速探究流",
        "description": "适合短课时或快速备课：观察起点、问题提出、科学探究。",
        "stages": [
            stage_item(
                id="observe",
                name="观察起点",
                expert="情境探寻专家",
                agent_id="stage_observation_start",
                direction_key="observation_start",
            ),
            stage_item(
                id="ask",
                name="问题提出",
                expert="问题提炼导师",
                agent_id="stage_question_refine",
                direction_key="question_refine",
            ),
            stage_item(
                id="investigate",
                name="科学探究",
                expert="实验设计专家",
                agent_id="stage_experiment_design",
                direction_key="experiment_design",
            ),
        ],
    },
    "steam_project": {
        "name": "steam_project",
        "display_name": "STEAM 项目化探究流",
        "description": "面向跨学科项目制课堂，强调原型制作、证据迭代和成果展示。",
        "stages": [
            stage_item(
                id="scenario",
                name="真实情境",
                expert="项目情境设计师",
                agent_id="stage_observation_start",
                direction_key="observation_start",
            ),
            stage_item(
                id="challenge",
                name="工程挑战",
                expert="挑战定义导师",
                agent_id="stage_question_refine",
                direction_key="question_refine",
            ),
            stage_item(
                id="prototype",
                name="原型制作",
                expert="原型迭代教练",
                agent_id="stage_experiment_design",
                direction_key="experiment_design",
            ),
            stage_item(
                id="showcase",
                name="展示评价",
                expert="学习评价设计师",
                agent_id="stage_extension",
                direction_key="extension",
            ),
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

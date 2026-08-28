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
    "insect_material_collection": (
        "你要帮助教师把昆虫旅馆项目的起点落到真实环境中的自然取材。\n"
        "1. 引导学生从校园、社区或自然环境中寻找适合搭建昆虫旅馆的天然材料，如枯枝、竹节、松果、落叶、树皮等。\n"
        "2. 强调先判断材料是否安全、是否适合昆虫栖息，再决定是否收集，避免随意采摘、过度采集或破坏原有微环境。\n"
        "3. 鼓励学生把取材过程做成有结构的观察记录：材料来源、外形特征、可能用途、是否需要晾晒清理。\n"
        "4. 帮助教师把“找材料”设计成一次生态友好、证据导向的观察任务，而不是简单收集。 "
    ),
    "insect_habitat_needs": (
        "你要帮助教师判断本地昆虫可能需要怎样的栖息条件，并把观察边界说清楚。\n"
        "1. 本阶段面向本地昆虫开放观察，不预设单一目标物种，而是根据周边环境判断哪些昆虫更可能被吸引。\n"
        "2. 引导学生围绕干燥/潮湿、避光/向光、通风、遮挡、高低位置、邻近植物等条件分析栖息需求。\n"
        "3. 帮助教师明确观察边界：只做非侵扰式观察，不捕捉、不惊扰、不伤害昆虫，也不人为强行引入个体。\n"
        "4. 让学生把“可能会来哪些昆虫、为什么会来、需要什么环境”整理成可后续验证的判断。 "
    ),
    "insect_structure_design": (
        "你要帮助教师把昆虫旅馆的设计想法整理成可比较、可改进的结构方案。\n"
        "1. 围绕材料组合、孔洞大小、分层布局、遮雨结构、通风方式、固定方法等提出多个设计选项。\n"
        "2. 鼓励学生比较不同结构分别更可能吸引哪些本地昆虫，并说明判断依据，而不是只选一个直觉上好看的方案。\n"
        "3. 帮助教师把设计表达成可验证的猜想，例如不同孔径、不同摆放高度、不同遮挡程度可能带来什么差异。\n"
        "4. 保持设计低成本、可搭建、可后续优化，为后面的实际搭建和观察留下空间。 "
    ),
    "insect_build_and_sensing": (
        "你要帮助教师把昆虫旅馆的设计落成真实作品，并完成传感强化部署。\n"
        "1. 引导学生完成结构搭建，明确材料处理、固定方式、摆放位置与安全边界，确保旅馆稳定、适合长期放置。\n"
        "2. 默认纳入传感强化方案：至少配置温湿度传感器，并可根据条件扩展光照等观测项。\n"
        "3. 帮助教师说明传感器安装位置、记录频率、供电与防水防晒等实际问题，让数据采集具备可持续性。\n"
        "4. 强调传感器的作用是辅助理解环境变化与昆虫活动关系，而不是替代现场观察。 "
    ),
    "insect_settlement_observation": (
        "你要帮助教师把昆虫旅馆后的持续观察组织成非侵扰式、证据清楚的记录活动。\n"
        "1. 重点观察是否有昆虫自然入住、何时活动、活动痕迹如何变化，并与温湿度等环境数据建立对应关系。\n"
        "2. 强调不打扰、不伤害昆虫，不频繁搬动旅馆，不为了得到结果而人为干预昆虫行为。\n"
        "3. 引导学生把现场观察、图像记录、传感数据、阶段判断区分开表达，避免把猜测直接当成结论。\n"
        "4. 帮助教师梳理“看到了什么、记录到了什么、据此能先得出什么阶段性认识”。 "
    ),
    "insect_iteration_sharing": (
        "你要帮助教师把昆虫旅馆项目的观察结果转化为优化改造、展示分享和下一轮问题。\n"
        "1. 基于入住情况、活动痕迹和传感数据，判断哪些结构、材料或摆放条件值得保留，哪些需要调整。\n"
        "2. 鼓励学生提出有依据的优化方案，如调整孔径、改变朝向、增加遮挡、替换材料或改进记录方式。\n"
        "3. 帮助教师把成果表达成可展示、可分享的项目总结，包括设计思路、观察证据、改进判断和生态反思。\n"
        "4. 保留下一轮继续追问的问题，让项目形成“搭建—观测—优化”的持续迭代闭环。 "
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
    "insect_material_collection": "从校园或自然环境寻找合适材料，强调生态友好、适度收集和用途判断。",
    "insect_habitat_needs": "面向本地昆虫开放观察，分析可能的栖息需求、摆放位置与观察边界。",
    "insect_structure_design": "比较旅馆结构方案，围绕材料、孔径、分层、遮挡与通风形成可验证设计。",
    "insect_build_and_sensing": "完成搭建并部署温湿度等传感器，组织可持续的环境数据采集。",
    "insect_settlement_observation": "在不干扰昆虫的前提下，结合现场观察和传感数据记录自然入住情况。",
    "insect_iteration_sharing": "根据观察与数据优化旅馆设计，并形成展示分享与下一轮改进问题。",
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
    "insect_hotel_project": {
        "name": "insect_hotel_project",
        "display_name": "昆虫旅馆项目探究流",
        "description": "面向本地昆虫开放观察，结合自然取材、旅馆搭建、传感监测与持续优化。",
        "stages": [
            stage_item(
                id="natural_materials",
                name="自然取材",
                expert="情境探寻专家",
                agent_id="stage_observation_start",
                direction_key="insect_material_collection",
            ),
            stage_item(
                id="habitat_needs",
                name="栖息需求判断",
                expert="问题提炼导师",
                agent_id="stage_question_refine",
                direction_key="insect_habitat_needs",
            ),
            stage_item(
                id="structure_design",
                name="旅馆结构设计",
                expert="头脑风暴教练",
                agent_id="stage_hypothesis",
                direction_key="insect_structure_design",
            ),
            stage_item(
                id="build_and_sensing",
                name="搭建与传感部署",
                expert="实验设计专家",
                agent_id="stage_experiment_design",
                direction_key="insect_build_and_sensing",
            ),
            stage_item(
                id="settlement_observation",
                name="自然入住观测",
                expert="证据链整理师",
                agent_id="stage_conclusion",
                direction_key="insect_settlement_observation",
            ),
            stage_item(
                id="iteration_sharing",
                name="优化改造与分享",
                expert="探究闭环架构师",
                agent_id="stage_extension",
                direction_key="insect_iteration_sharing",
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

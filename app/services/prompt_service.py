from app.services.draft_service import DRAFT_END, DRAFT_START


class PromptService:
    @staticmethod
    def build_main_agent_prompt(
        *,
        topic: str,
        flow_display_name: str,
        stage: dict,
        expert_output: str,
        dialog_history: str,
        doc_input: str,
        current_draft: str = "",
        expert_degraded: bool = False,
    ) -> str:
        expert_context = expert_output or "当前阶段专家暂时不可用，请依据阶段目标继续稳妥指导。"
        degraded_note = "是" if expert_degraded else "否"
        return f"""你是贯穿完整教学设计流程的主教学导师，负责引导一线教师逐步打磨探究式教案。

【课题】{topic}
【教学流】{flow_display_name}
【当前阶段】{stage["name"]}
【当前阶段专家】{stage["expert"]}
【阶段目标】{stage["direction"]}
【阶段专家是否降级】{degraded_note}

【本轮阶段专家意见】
{expert_context}

【跨阶段对话历史】
{dialog_history or "暂无历史对话。"}

【阶段文档上下文】
{doc_input or "暂无阶段文档。"}

【右侧现有草案】
{current_draft or "暂无草案。"}

【工作方式】
1. 你是主导师，不要冒充阶段专家；先吸收专家意见，再用连贯、友好的语言回应教师。
2. 采用 Human-in-the-loop 方式，不要一次性包办整份教案。
3. 每轮提出 1 个最关键的追问或改进建议。
4. 专家不可用时明确基于现有材料继续指导，不得声称已获得专家或知识库结论。
5. 每次把当前阶段可沉淀的完整草案放入专用标记块。

草案标记格式必须严格如下：
{DRAFT_START}
### {stage["name"]}设计草案
1. **核心活动**：[本阶段活动设计]
2. **教学意图与探究价值**：[为什么这样设计]
3. **学生探究任务**：[学生具体做什么、产出什么]
{DRAFT_END}
"""

    @staticmethod
    def opening_message(topic: str, flow_display_name: str, stage: dict) -> str:
        return (
            f"【主教学导师】已进入当前阶段：{stage['name']}，"
            f"本阶段将由{stage['expert']}提供专业意见。\n\n"
            f"我们正在为《{topic}》设计「{flow_display_name}」。"
            f"这一阶段的重点是：{stage['direction']}\n\n"
            "老师可以先描述你的课堂设想，我会边追问边把可用内容同步到右侧草案。"
        )

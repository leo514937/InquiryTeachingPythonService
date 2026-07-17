import asyncio
from collections.abc import AsyncIterator

from app.core.config import DifyAgentConfig, get_settings
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService


class DifyAgentError(RuntimeError):
    pass


class DifyAgentService:
    @staticmethod
    def list_agents(flow_name: str | None = None) -> list[DifyAgentConfig]:
        agents = get_settings().dify_stage_agents()
        if not flow_name:
            return agents
        return [
            agent
            for agent in agents
            if not agent.flow_names or flow_name in agent.flow_names
        ]

    @staticmethod
    def find_agent(agent_id: str, flow_name: str | None = None) -> DifyAgentConfig | None:
        for agent in DifyAgentService.list_agents(flow_name):
            if agent.id == agent_id:
                return agent
        return None

    @staticmethod
    async def chat_stream(
        *,
        agent: DifyAgentConfig,
        session_id: str,
        conversation_id: str,
        flow_display_name: str,
        topic: str,
        stage: dict,
        message: str,
        dialog_history: str,
        doc_input: str,
        current_draft: str,
        selection_text: str = "",
    ) -> AsyncIterator[dict]:
        settings = get_settings()
        system_prompt = PromptService.build_stage_agent_prompt(
            topic=topic,
            flow_display_name=flow_display_name,
            stage=stage,
            dialog_history=dialog_history,
            doc_input=doc_input,
            current_draft=current_draft,
            user_message=message,
            selection_text=selection_text,
        )

        if settings.llm_api_key:
            conversation_key = conversation_id or f"llm_{session_id}_{agent.id}"
            async for text in LLMService.chat_stream(system_prompt, [], message):
                yield {
                    "text": text,
                    "conversation_id": conversation_key,
                }
            return

        async for event in DifyAgentService._mock_agent_stream(
            agent,
            stage,
            message,
            conversation_id,
            selection_text,
        ):
            yield event

    @staticmethod
    async def _mock_agent_stream(
        agent: DifyAgentConfig,
        stage: dict,
        message: str,
        conversation_id: str,
        selection_text: str = "",
    ) -> AsyncIterator[dict]:
        next_conversation_id = conversation_id or f"mock_{agent.id}"
        if selection_text.strip():
            reply = (
                f"【{agent.name}】针对“{stage['name']}”阶段，我先只围绕你选中的这段内容来点评。"
                f"结合教师当前输入“{message}”，这段内容更需要补齐与“{stage['direction']}”相关的关键证据、判断依据和追问设计。"
            )
        else:
            reply = (
                f"【{agent.name}】针对“{stage['name']}”阶段，我建议先围绕“{stage['direction']}”展开。"
                f"结合教师当前输入“{message}”，可以优先补齐学生可观察对象、需要记录的证据，"
                "并设计一个能推动学生继续追问的关键问题。"
            )
        for index in range(0, len(reply), 12):
            await asyncio.sleep(0.01)
            yield {
                "text": reply[index : index + 12],
                "conversation_id": next_conversation_id,
            }

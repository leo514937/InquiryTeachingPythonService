import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import DifyAgentConfig, get_settings


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
        flow_name: str,
        topic: str,
        stage: dict,
        message: str,
        dialog_history: str,
        doc_input: str,
        current_draft: str,
    ) -> AsyncIterator[dict]:
        settings = get_settings()
        if settings.dify_stage_agent_mode == "mock":
            async for event in DifyAgentService._mock_agent_stream(
                agent,
                stage,
                message,
                conversation_id,
            ):
                yield event
            return

        if not agent.api_url or not agent.api_key:
            raise DifyAgentError(f"阶段专家 {agent.id} 未配置 Dify API")

        payload = {
            "query": message or "请继续指导这个阶段的教案设计",
            "inputs": {
                "Flow": flow_name,
                "topic": topic,
                "stage_id": stage["id"],
                "stage_name": stage["name"],
                "stage_goal": stage["direction"],
                "human_input": message,
                "dialog_history": dialog_history or " ",
                "doc_input": doc_input or " ",
                "current_draft": current_draft or " ",
            },
            "response_mode": "streaming",
            "conversation_id": conversation_id or "",
            "user": session_id,
            "auto_generate_name": True,
        }
        headers = {
            "Authorization": f"Bearer {agent.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                async with client.stream("POST", agent.api_url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise DifyAgentError(
                            f"阶段专家 {agent.id} 返回 HTTP {response.status_code}: {body[:300]}"
                        )

                    received_text = False
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue

                        if data.get("event") in {"error", "workflow_failed"}:
                            raise DifyAgentError(
                                str(data.get("message") or data.get("error") or "Dify 工作流执行失败")
                            )
                        next_conversation_id = data.get("conversation_id") or conversation_id
                        answer = data.get("answer") or data.get("text") or ""
                        if answer:
                            received_text = True
                            yield {
                                "text": answer,
                                "conversation_id": next_conversation_id,
                            }
                    if not received_text:
                        raise DifyAgentError(f"阶段专家 {agent.id} 未返回有效文本")
        except DifyAgentError:
            raise
        except Exception as exc:
            raise DifyAgentError(f"阶段专家 {agent.id} 调用失败: {exc}") from exc

    @staticmethod
    async def _mock_agent_stream(
        agent: DifyAgentConfig,
        stage: dict,
        message: str,
        conversation_id: str,
    ) -> AsyncIterator[dict]:
        next_conversation_id = conversation_id or f"mock_{agent.id}"
        reply = (
            f"【{agent.name}】从“{stage['name']}”的专业视角看，教师提出的“{message}”"
            "已经具备形成课堂活动的基础。建议进一步明确学生可观察的对象、需要记录的证据，"
            "以及教师用于推动学生解释和修正想法的关键追问。"
        )
        for index in range(0, len(reply), 12):
            await asyncio.sleep(0.01)
            yield {
                "text": reply[index : index + 12],
                "conversation_id": next_conversation_id,
            }

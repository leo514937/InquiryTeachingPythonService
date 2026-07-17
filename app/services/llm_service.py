import asyncio
import json
from typing import Literal

import httpx

from app.core.config import get_settings


LLMResponseKind = Literal["guide", "draft_generate", "draft_edit", "draft_target"]


class LLMService:
    @staticmethod
    async def chat_stream(
        system_prompt: str,
        history_messages: list[dict],
        new_message: str,
        *,
        response_kind: LLMResponseKind = "guide",
    ):
        settings = get_settings()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": new_message})

        if not settings.llm_api_key:
            async for chunk in LLMService._mock_chat_stream(system_prompt, new_message, response_kind=response_kind):
                yield chunk
            return

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        if settings.llm_http_referer:
            headers["HTTP-Referer"] = settings.llm_http_referer
        if settings.llm_app_title:
            headers["X-Title"] = settings.llm_app_title
        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0.7,
            "reasoning": {"enabled": settings.llm_reasoning_enabled},
            "stream": True,
        }
        url = f"{settings.llm_api_base.rstrip('/')}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        async for chunk in LLMService._mock_chat_stream(system_prompt, new_message, response_kind=response_kind):
                            yield chunk
                        return
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"].get("content", "")
                        except Exception:
                            delta = ""
                        if delta:
                            yield delta
        except Exception:
            async for chunk in LLMService._mock_chat_stream(system_prompt, new_message, response_kind=response_kind):
                yield chunk

    @staticmethod
    async def complete_text(
        system_prompt: str,
        history_messages: list[dict],
        new_message: str,
        *,
        response_kind: LLMResponseKind = "guide",
    ) -> str:
        chunks: list[str] = []
        async for chunk in LLMService.chat_stream(
            system_prompt,
            history_messages,
            new_message,
            response_kind=response_kind,
        ):
            chunks.append(chunk)
        return "".join(chunks)

    @staticmethod
    async def _mock_chat_stream(system_prompt: str, new_message: str, *, response_kind: LLMResponseKind = "guide"):
        if response_kind == "draft_generate":
            async for chunk in LLMService._mock_draft_generate_stream(system_prompt, new_message):
                yield chunk
            return
        if response_kind == "draft_edit":
            async for chunk in LLMService._mock_draft_edit_stream(system_prompt, new_message):
                yield chunk
            return
        if response_kind == "draft_target":
            async for chunk in LLMService._mock_draft_target_stream(system_prompt, new_message):
                yield chunk
            return

        async for chunk in LLMService._mock_guide_stream(system_prompt, new_message):
            yield chunk

    @staticmethod
    async def _mock_guide_stream(system_prompt: str, new_message: str):
        stage_name = LLMService._between(system_prompt, "【当前阶段】", "\n") or "当前阶段"
        stage_goal = LLMService._between(system_prompt, "【阶段目标】", "\n\n") or "阶段目标"
        selection_text = LLMService._between(system_prompt, "【教师当前选中的草案内容】", "【本轮教师输入】")
        if selection_text and selection_text != "本轮无选区。":
            guide_hint = "我会先围绕你选中的这段内容来推进，重点看它和当前阶段目标是否对齐、还缺少哪些证据或追问。"
            full_reply = (
                f"【流程引导Agent】：老师，我收到你的想法：“{new_message}”。\n\n"
                f"你刚刚选中的这段内容很关键。站在“{stage_name}”这一阶段，我们要先把它和{stage_goal}更紧地扣在一起。\n\n"
                f"{guide_hint}\n\n"
                "你可以继续补充这段想解决的课堂问题、学生反应或你最担心的地方，我会继续围绕这段帮你收紧。"
            )
        else:
            guide_hint = "你可以先补充一个更具体的课堂情境，或者说明希望学生优先观察什么现象。"
            full_reply = (
                f"【流程引导Agent】：老师，我收到你的想法：“{new_message}”。\n\n"
                f"站在“{stage_name}”这一阶段，我们要先把{stage_goal}落到可观察、可追问、可推进的课堂动作上。\n\n"
                f"{guide_hint}\n\n"
                "你可以继续补充课堂材料、学生已有基础或预期现象，我会继续帮你把方向收紧。"
            )

        for index in range(0, len(full_reply), 12):
            await asyncio.sleep(0.01)
            yield full_reply[index : index + 12]

    @staticmethod
    async def _mock_draft_generate_stream(system_prompt: str, new_message: str):
        stage_name = LLMService._between(system_prompt, "【当前阶段】", "\n") or "当前阶段"
        stage_goal = LLMService._between(system_prompt, "【阶段目标】", "\n\n") or "阶段目标"

        draft = (
            f"### {stage_name}设计草案\n\n"
            f"**阶段目标**：{stage_goal}\n\n"
            f"**流程引导承接**：基于教师输入“{new_message}”继续推进课堂设计。\n\n"
            "1. **核心活动**：围绕教师提出的课堂设想，设计一个学生能够直接观察、讨论并形成证据的探究活动。\n"
            "2. **教学意图与探究价值**：让学生从现象进入问题，再通过证据形成解释，避免直接接受结论。\n"
            "3. **学生探究任务**：学生以小组为单位记录现象、提出猜想、整理证据，并用简短语言表达推理过程。\n"
            "4. **草案优化提示**：如果课堂材料或学生基础发生变化，可以进一步细化变量、步骤和记录方式。"
        )

        for index in range(0, len(draft), 12):
            await asyncio.sleep(0.01)
            yield draft[index : index + 12]

    @staticmethod
    async def _mock_draft_edit_stream(system_prompt: str, new_message: str):
        target_text = LLMService._between(system_prompt, "【本次需要修改的原片段正文】", "【教师修改要求】") or "请补充这一段的细节。"
        updated = target_text.strip()
        if not updated:
            updated = "请补充这一段的细节。"

        addition = f"\n\n- 根据教师这轮要求“{new_message}”，这里补充了更具体的说明。"
        full_reply = f"{updated}{addition}".strip()

        for index in range(0, len(full_reply), 12):
            await asyncio.sleep(0.01)
            yield full_reply[index : index + 12]

    @staticmethod
    async def _mock_draft_target_stream(system_prompt: str, new_message: str):
        target_summary = f"我猜测最需要修改的是与“{new_message}”最相关的那一段。"
        for index in range(0, len(target_summary), 12):
            await asyncio.sleep(0.01)
            yield target_summary[index : index + 12]

    @staticmethod
    def _between(text: str, start: str, end: str) -> str:
        if start not in text:
            return ""
        part = text.split(start, 1)[1]
        if end in part:
            part = part.split(end, 1)[0]
        return part.strip()

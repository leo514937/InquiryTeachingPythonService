import asyncio
import json

import httpx

from app.core.config import get_settings


class LLMService:
    @staticmethod
    async def chat_stream(system_prompt: str, history_messages: list[dict], new_message: str):
        settings = get_settings()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": new_message})

        if not settings.llm_api_key:
            async for chunk in LLMService._mock_chat_stream(system_prompt, new_message):
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
                        async for chunk in LLMService._mock_chat_stream(system_prompt, new_message):
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
            async for chunk in LLMService._mock_chat_stream(system_prompt, new_message):
                yield chunk

    @staticmethod
    async def _mock_chat_stream(system_prompt: str, new_message: str):
        stage_name = LLMService._between(system_prompt, "【当前阶段】", "\n") or "当前阶段"
        expert_output = LLMService._between(system_prompt, "【本轮阶段专家意见】", "\n\n")

        draft = (
            f"### {stage_name}设计草案\n"
            f"1. **核心活动**：围绕“{new_message}”设计一个可观察、可记录、可讨论的探究活动。\n"
            "2. **教学意图与探究价值**：让学生从现象进入问题，再通过证据形成解释，避免直接接受结论。\n"
            "3. **学生探究任务**：学生以小组为单位记录现象、提出猜想、整理证据，并用简短语言表达推理过程。"
        )
        full_reply = (
            f"【主教学导师】：老师，我收到你的想法：“{new_message}”。\n\n"
            f"本阶段专家给出的核心提醒是：{expert_output or '当前专家暂时不可用，我将依据阶段目标继续协助。'}\n\n"
            f"这个切入点可以继续打磨。站在“{stage_name}”这一阶段，我们先把学生真正能看见、能操作、能追问的部分抓出来。"
            "我建议你再补充一个具体课堂情境：学生第一眼看到什么现象，随后会自然提出什么问题？\n\n"
            f"===DRAFT_START===\n{draft}\n===DRAFT_END===\n\n"
            "你可以继续说说课堂材料、学生年龄段或已有知识基础，我再帮你把草案压实。"
        )

        for index in range(0, len(full_reply), 12):
            await asyncio.sleep(0.01)
            yield full_reply[index : index + 12]

    @staticmethod
    def _between(text: str, start: str, end: str) -> str:
        if start not in text:
            return ""
        part = text.split(start, 1)[1]
        if end in part:
            part = part.split(end, 1)[0]
        return part.strip()

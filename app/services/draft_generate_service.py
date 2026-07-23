from __future__ import annotations

from collections.abc import AsyncIterator

from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService


class DraftGenerateService:
    @staticmethod
    async def stream_candidate(
        *,
        topic: str,
        flow_display_name: str,
        stage: dict,
        dialog_history: str,
        doc_input: str,
        current_draft: str,
        user_message: str,
        llm_history: list[dict],
    ) -> AsyncIterator[tuple[str, str]]:
        prompt = PromptService.build_draft_generate_prompt(
            topic=topic,
            flow_display_name=flow_display_name,
            stage=stage,
            dialog_history=dialog_history,
            doc_input=doc_input,
            current_draft=current_draft,
            user_message=user_message,
        )
        candidate = ""
        async for chunk in LLMService.chat_stream(
            prompt,
            llm_history,
            user_message,
            response_kind="draft_generate",
        ):
            if not chunk:
                continue
            candidate += chunk
            yield candidate, chunk

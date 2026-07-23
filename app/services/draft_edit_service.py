from __future__ import annotations

from collections.abc import AsyncIterator

from app.services.draft_target_resolver import DraftTarget
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService


class DraftEditService:
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
        target: DraftTarget,
    ) -> AsyncIterator[tuple[str, str, str]]:
        prompt = PromptService.build_draft_edit_prompt(
            topic=topic,
            flow_display_name=flow_display_name,
            stage=stage,
            dialog_history=dialog_history,
            doc_input=doc_input,
            current_draft=current_draft,
            user_message=user_message,
            target_summary=target.target_summary,
            target_text=target.target_text,
        )
        replacement = ""
        async for chunk in LLMService.chat_stream(
            prompt,
            llm_history,
            user_message,
            response_kind="draft_edit",
        ):
            if not chunk:
                continue
            replacement += chunk
            yield (
                DraftEditService.apply_replacement(current_draft, target, replacement),
                replacement,
                chunk,
            )

    @staticmethod
    def apply_replacement(current_draft: str, target: DraftTarget, replacement: str) -> str:
        replacement = replacement.rstrip()
        return f"{current_draft[:target.start_offset]}{replacement}{current_draft[target.end_offset:]}"

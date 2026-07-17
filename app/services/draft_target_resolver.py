from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DraftTarget:
    mode: str
    start_offset: int
    end_offset: int
    target_text: str
    target_summary: str


class DraftTargetResolver:
    @staticmethod
    def resolve(*, current_draft: str, selection: dict | None = None) -> DraftTarget | None:
        if not current_draft.strip():
            return None

        return DraftTargetResolver._from_selection(current_draft, selection)

    @staticmethod
    def _from_selection(current_draft: str, selection: dict | None) -> DraftTarget | None:
        if not selection:
            return None
        selected_text = (selection.get("selected_text") or "").strip()
        if not selected_text:
            return None

        start_offset = int(selection.get("start_offset") or 0)
        end_offset = int(selection.get("end_offset") or 0)
        if 0 <= start_offset < end_offset <= len(current_draft):
            target_text = current_draft[start_offset:end_offset]
            if target_text.strip():
                return DraftTarget(
                    mode="selection",
                    start_offset=start_offset,
                    end_offset=end_offset,
                    target_text=target_text,
                    target_summary=DraftTargetResolver._summarize(target_text),
                )

        direct_index = current_draft.find(selected_text)
        if direct_index >= 0:
            return DraftTarget(
                mode="selection",
                start_offset=direct_index,
                end_offset=direct_index + len(selected_text),
                target_text=selected_text,
                target_summary=DraftTargetResolver._summarize(selected_text),
            )
        return None

    @staticmethod
    def _summarize(text: str, limit: int = 72) -> str:
        compact = re.sub(r"\s+", " ", (text or "").strip())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

DRAFT_START = "===DRAFT_START==="
DRAFT_END = "===DRAFT_END==="


class DraftService:
    @staticmethod
    def extract_draft(text: str) -> str:
        if DRAFT_START not in text:
            return ""
        draft_part = text.split(DRAFT_START, 1)[1]
        if DRAFT_END in draft_part:
            draft_part = draft_part.split(DRAFT_END, 1)[0]
        return draft_part.strip()

    @staticmethod
    def strip_draft_markers(text: str) -> str:
        if DRAFT_START not in text:
            return text
        before, after_start = text.split(DRAFT_START, 1)
        if DRAFT_END not in after_start:
            return before.strip()
        after = after_start.split(DRAFT_END, 1)[1]
        return (before + after).strip()

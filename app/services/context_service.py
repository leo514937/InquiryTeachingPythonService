from sqlalchemy.orm import Session

from app.db.models import MessageModel, StageOutputModel


MAX_DIALOG_CHARS = 60_000


class ContextService:
    @staticmethod
    def load_messages(db: Session, session_id: str) -> list[MessageModel]:
        return (
            db.query(MessageModel)
            .filter(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
            .all()
        )

    @staticmethod
    def format_dialog_history(messages: list[MessageModel], max_chars: int = MAX_DIALOG_CHARS) -> str:
        records = []
        for item in messages:
            if item.role == "user":
                speaker = "教师"
            elif item.message_type == "stage_expert":
                speaker = f"阶段专家-{item.agent_id or 'unknown'}"
            elif item.message_type == "draft_tutor":
                speaker = "草案修订Agent"
            else:
                speaker = "主教学导师"
            records.append(f"{speaker}: {item.content}\n")

        selected = []
        used = len("<dialog_history>\n</dialog_history>")
        for record in reversed(records):
            if used + len(record) > max_chars:
                break
            selected.append(record)
            used += len(record)
        selected.reverse()
        return "<dialog_history>\n" + "".join(selected) + "</dialog_history>"

    @staticmethod
    def to_llm_history(messages: list[MessageModel], max_chars: int = MAX_DIALOG_CHARS) -> list[dict]:
        selected = []
        used = 0
        for item in reversed(messages):
            if item.role == "user":
                content = item.content
                role = "user"
            elif item.message_type == "stage_expert":
                content = f"【阶段专家意见】{item.content}"
                role = "assistant"
            elif item.message_type == "draft_tutor":
                content = f"【草案修订】{item.content}"
                role = "assistant"
            else:
                content = item.content
                role = "assistant"
            if used + len(content) > max_chars:
                break
            selected.append({"role": role, "content": content})
            used += len(content)
        selected.reverse()
        return selected

    @staticmethod
    def build_doc_input(
        db: Session,
        session_id: str,
        current_stage_id: str,
    ) -> str:
        outputs = (
            db.query(StageOutputModel)
            .filter(StageOutputModel.session_id == session_id)
            .order_by(StageOutputModel.order_index.asc())
            .all()
        )
        sections = []
        for output in outputs:
            if output.stage_id == current_stage_id:
                sections.append(
                    f"## 当前阶段：{output.stage_name}\n"
                    f"{output.draft_content or '当前阶段暂无草稿。'}"
                )
                break
            if output.confirmed and output.final_content:
                sections.append(f"## 已定稿：{output.stage_name}\n{output.final_content}")
        return "\n\n".join(sections) or "暂无已定稿阶段内容，当前阶段暂无草稿。"

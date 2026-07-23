from sqlalchemy import inspect, text

from app.db.database import engine


def ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    if "chat_turns" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        chat_turn_columns = {column["name"] for column in inspector.get_columns("chat_turns")}
        if "expert_message_id" not in chat_turn_columns:
            connection.execute(
                text("ALTER TABLE chat_turns ADD COLUMN expert_message_id VARCHAR")
            )

        session_columns = {column["name"] for column in inspector.get_columns("sessions")}
        if "draft_mode_enabled" not in session_columns:
            connection.execute(
                text("ALTER TABLE sessions ADD COLUMN draft_mode_enabled INTEGER DEFAULT 0")
            )

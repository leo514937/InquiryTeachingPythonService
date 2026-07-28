from sqlalchemy import inspect, text

from app.db.database import engine


def ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "chat_turns" in table_names:
            chat_turn_columns = {column["name"] for column in inspector.get_columns("chat_turns")}
            if "expert_message_id" not in chat_turn_columns:
                connection.execute(
                    text("ALTER TABLE chat_turns ADD COLUMN expert_message_id VARCHAR")
                )

        if "sessions" in table_names:
            session_columns = {column["name"] for column in inspector.get_columns("sessions")}
            if "draft_mode_enabled" not in session_columns:
                connection.execute(
                    text("ALTER TABLE sessions ADD COLUMN draft_mode_enabled INTEGER DEFAULT 0")
                )
            if "owner_user_id" not in session_columns:
                connection.execute(
                    text("ALTER TABLE sessions ADD COLUMN owner_user_id VARCHAR")
                )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_sessions_owner_user_id "
                    "ON sessions (owner_user_id)"
                )
            )

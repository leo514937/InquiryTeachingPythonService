from sqlalchemy import inspect, text

from app.db.database import engine


def ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    if "chat_turns" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chat_turns")}
    if "expert_message_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE chat_turns ADD COLUMN expert_message_id VARCHAR")
            )

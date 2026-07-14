from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from textwrap import dedent

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
DOCS_DIR = ROOT / "docs"


def ensure_env_file() -> None:
    if ENV_FILE.exists() or not ENV_EXAMPLE.exists():
        return
    ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


def ensure_docs_dir() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def init_database() -> None:
    load_dotenv(ENV_FILE)
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'app.db').as_posix()}")
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
    else:
        db_path = ROOT / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    ddl = [
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            topic TEXT NOT NULL,
            flow_name TEXT NOT NULL DEFAULT 'inquiry_7_stage',
            current_stage_index INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            agent_id TEXT,
            message_type TEXT DEFAULT 'chat',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            user_message_id TEXT NOT NULL,
            expert_message_id TEXT,
            assistant_message_id TEXT NOT NULL,
            rag_record_id TEXT,
            draft_before TEXT DEFAULT '',
            draft_after TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stage_outputs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            flow_name TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            draft_content TEXT DEFAULT '',
            final_content TEXT DEFAULT '',
            confirmed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(session_id, stage_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS rag_records (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            query TEXT,
            context TEXT,
            source_json TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_conversations (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            conversation_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(session_id, agent_id)
        )
        """,
    ]

    with sqlite3.connect(db_path) as conn:
        for statement in ddl:
            conn.execute(statement)
        chat_turn_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(chat_turns)").fetchall()
        }
        if "expert_message_id" not in chat_turn_columns:
            conn.execute("ALTER TABLE chat_turns ADD COLUMN expert_message_id TEXT")
        conn.commit()


def main() -> None:
    ensure_env_file()
    ensure_docs_dir()
    init_database()
    print(
        dedent(
            f"""
            Bootstrap complete.

            Service root: {ROOT}
            Database: {ROOT / 'app.db'}

            Next steps:
              1. Backend:  python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
              2. Frontend: cd frontend && npm install && npm run dev
              3. Docs:     open docs/README.md for the day-by-day task list
            """
        ).strip()
    )


if __name__ == "__main__":
    main()

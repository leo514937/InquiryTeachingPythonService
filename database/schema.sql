-- InquiryTeachingPythonService - SQLite schema
-- Covers sessions, seven-stage outputs, messages, rollback turns,
-- RAG records, and per-agent Dify conversation state.

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Teaching-design session and workflow cursor.
CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    title               TEXT,
    topic               TEXT NOT NULL,
    flow_name           TEXT NOT NULL DEFAULT 'inquiry_7_stage',
    current_stage_index INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Draft and confirmed output for every stage in a session.
CREATE TABLE IF NOT EXISTS stage_outputs (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    flow_name     TEXT NOT NULL,
    stage_id      TEXT NOT NULL,
    stage_name    TEXT NOT NULL,
    order_index   INTEGER NOT NULL,
    draft_content TEXT NOT NULL DEFAULT '',
    final_content TEXT NOT NULL DEFAULT '',
    confirmed     INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    CONSTRAINT uq_session_stage UNIQUE (session_id, stage_id),
    CONSTRAINT fk_stage_outputs_session
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- Teacher, stage-expert, and main-tutor messages.
CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    stage_id     TEXT NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    agent_id     TEXT,
    message_type TEXT NOT NULL DEFAULT 'chat',
    created_at   TEXT NOT NULL,
    CONSTRAINT fk_messages_session
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- RAG request, retrieved context, and serialized source metadata.
CREATE TABLE IF NOT EXISTS rag_records (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    stage_id    TEXT NOT NULL,
    query       TEXT,
    context     TEXT,
    source_json TEXT,
    created_at  TEXT NOT NULL,
    CONSTRAINT fk_rag_records_session
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- Independent Dify conversation state for each session and stage agent.
CREATE TABLE IF NOT EXISTS agent_conversations (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    agent_id         TEXT NOT NULL,
    conversation_id TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    CONSTRAINT uq_session_agent UNIQUE (session_id, agent_id),
    CONSTRAINT fk_agent_conversations_session
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- One rollback unit per chat round. Message IDs are application-managed
-- references because rollback currently deletes messages before this row.
CREATE TABLE IF NOT EXISTS chat_turns (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id              TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    stage_id             TEXT NOT NULL,
    user_message_id      TEXT NOT NULL,
    expert_message_id    TEXT,
    assistant_message_id TEXT NOT NULL,
    rag_record_id        TEXT,
    draft_before         TEXT NOT NULL DEFAULT '',
    draft_after          TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    CONSTRAINT fk_chat_turns_session
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- Session timeline and stage lookup indexes.
CREATE INDEX IF NOT EXISTS ix_sessions_updated_at
    ON sessions (updated_at);

CREATE INDEX IF NOT EXISTS ix_stage_outputs_session_id
    ON stage_outputs (session_id);
CREATE INDEX IF NOT EXISTS ix_stage_outputs_stage_id
    ON stage_outputs (stage_id);
CREATE INDEX IF NOT EXISTS ix_stage_outputs_session_order
    ON stage_outputs (session_id, order_index);

CREATE INDEX IF NOT EXISTS ix_messages_session_id
    ON messages (session_id);
CREATE INDEX IF NOT EXISTS ix_messages_stage_id
    ON messages (stage_id);
CREATE INDEX IF NOT EXISTS ix_messages_session_created
    ON messages (session_id, created_at);

CREATE INDEX IF NOT EXISTS ix_rag_records_session_id
    ON rag_records (session_id);
CREATE INDEX IF NOT EXISTS ix_rag_records_session_stage
    ON rag_records (session_id, stage_id);

CREATE INDEX IF NOT EXISTS ix_agent_conversations_session_id
    ON agent_conversations (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_conversations_agent_id
    ON agent_conversations (agent_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_chat_turns_turn_id
    ON chat_turns (turn_id);
CREATE INDEX IF NOT EXISTS ix_chat_turns_session_id
    ON chat_turns (session_id);
CREATE INDEX IF NOT EXISTS ix_chat_turns_stage_id
    ON chat_turns (stage_id);
CREATE INDEX IF NOT EXISTS ix_chat_turns_session_id_desc
    ON chat_turns (session_id, id DESC);

COMMIT;

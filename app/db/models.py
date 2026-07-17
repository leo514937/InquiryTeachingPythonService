from sqlalchemy import Column, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    title = Column(String)
    topic = Column(String, nullable=False)
    flow_name = Column(String, nullable=False, default="inquiry_7_stage")
    current_stage_index = Column(Integer, default=0)
    status = Column(String, default="active")
    draft_mode_enabled = Column(Integer, default=0)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class AppSettingModel(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(String, nullable=False)


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    stage_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    agent_id = Column(String)
    message_type = Column(String, default="chat")
    created_at = Column(String, nullable=False)


class ChatTurnModel(Base):
    __tablename__ = "chat_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(String, nullable=False, unique=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    stage_id = Column(String, nullable=False, index=True)
    user_message_id = Column(String, nullable=False)
    expert_message_id = Column(String)
    assistant_message_id = Column(String, nullable=False)
    rag_record_id = Column(String)
    draft_before = Column(Text, default="")
    draft_after = Column(Text, default="")
    created_at = Column(String, nullable=False)


class StageOutputModel(Base):
    __tablename__ = "stage_outputs"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    flow_name = Column(String, nullable=False)
    stage_id = Column(String, nullable=False, index=True)
    stage_name = Column(String, nullable=False)
    order_index = Column(Integer, nullable=False)
    draft_content = Column(Text, default="")
    final_content = Column(Text, default="")
    confirmed = Column(Integer, default=0)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "stage_id", name="uq_session_stage"),)


class DraftProposalModel(Base):
    __tablename__ = "draft_proposals"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    stage_id = Column(String, nullable=False, index=True)
    base_content = Column(Text, default="")
    candidate_content = Column(Text, default="")
    diff_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="pending")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class RagRecordModel(Base):
    __tablename__ = "rag_records"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    stage_id = Column(String, nullable=False)
    query = Column(Text)
    context = Column(Text)
    source_json = Column(Text)
    created_at = Column(String, nullable=False)


class AgentConversationModel(Base):
    __tablename__ = "agent_conversations"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    conversation_id = Column(String, default="")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "agent_id", name="uq_session_agent"),)

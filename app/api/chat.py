import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.sse import format_sse
from app.db.database import SessionLocal, get_db
from app.db.models import (
    AgentConversationModel,
    ChatTurnModel,
    MessageModel,
    SessionModel,
    StageOutputModel,
)
from app.schemas import ChatRequest
from app.services.context_service import ContextService
from app.services.app_settings_service import SUBAGENT_MODE, get_global_chat_mode
from app.services.dify_agent_service import DifyAgentError, DifyAgentService
from app.services.draft_service import DraftService
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.workflow.flows import get_flow


router = APIRouter(prefix="/api/sessions", tags=["chat"])


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def get_current_context(
    db: Session,
    session_id: str,
) -> tuple[SessionModel, dict, dict, StageOutputModel | None]:
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    flow = get_flow(sess.flow_name)
    if sess.current_stage_index >= len(flow["stages"]):
        raise HTTPException(status_code=400, detail="Workflow completed")

    stage = flow["stages"][sess.current_stage_index]
    stage_output = (
        db.query(StageOutputModel)
        .filter(
            StageOutputModel.session_id == session_id,
            StageOutputModel.stage_id == stage["id"],
        )
        .first()
    )
    return sess, flow, stage, stage_output


def get_agent_conversation_id(db: Session, session_id: str, agent_id: str) -> str:
    row = (
        db.query(AgentConversationModel)
        .filter(
            AgentConversationModel.session_id == session_id,
            AgentConversationModel.agent_id == agent_id,
        )
        .first()
    )
    return row.conversation_id if row else ""


def upsert_agent_conversation_id(session_id: str, agent_id: str, conversation_id: str) -> None:
    if not conversation_id:
        return

    db = SessionLocal()
    try:
        row = (
            db.query(AgentConversationModel)
            .filter(
                AgentConversationModel.session_id == session_id,
                AgentConversationModel.agent_id == agent_id,
            )
            .first()
        )
        timestamp = now_iso()
        if row:
            row.conversation_id = conversation_id
            row.updated_at = timestamp
        else:
            db.add(
                AgentConversationModel(
                    id=new_id("aconv"),
                    session_id=session_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        db.commit()
    finally:
        db.close()


def save_chat_result(
    *,
    session_id: str,
    stage_id: str,
    user_message: str,
    expert_message: str = "",
    expert_agent_id: str,
    main_message: str = "",
    draft_content: str = "",
) -> dict:
    db = SessionLocal()
    try:
        turn_id = new_id("turn")
        user_msg_id = new_id("msg")
        expert_msg_id = None
        main_msg_id = None

        db.add(
            MessageModel(
                id=user_msg_id,
                session_id=session_id,
                stage_id=stage_id,
                role="user",
                content=user_message,
                agent_id=None,
                message_type="chat",
                created_at=now_iso(),
            )
        )

        if expert_message:
            expert_msg_id = new_id("msg")
            db.add(
                MessageModel(
                    id=expert_msg_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    role="assistant",
                    content=expert_message,
                    agent_id=expert_agent_id,
                    message_type="stage_expert",
                    created_at=now_iso(),
                )
            )

        assistant_message_id = expert_msg_id
        assistant_message_type = "stage_expert"
        assistant_message_agent_id = expert_agent_id
        main_timestamp = now_iso()
        if main_message:
            main_msg_id = new_id("msg")
            assistant_message_id = main_msg_id
            assistant_message_type = "main_tutor"
            assistant_message_agent_id = "main_agent"
            db.add(
                MessageModel(
                    id=main_msg_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    role="assistant",
                    content=DraftService.strip_draft_markers(main_message),
                    agent_id="main_agent",
                    message_type="main_tutor",
                    created_at=main_timestamp,
                )
            )

        output = (
            db.query(StageOutputModel)
            .filter(
                StageOutputModel.session_id == session_id,
                StageOutputModel.stage_id == stage_id,
            )
            .first()
        )
        draft_before = output.draft_content or "" if output else ""
        draft_after = draft_content or draft_before
        if output and draft_content and main_message:
            output.draft_content = draft_content
            output.updated_at = main_timestamp

        db.add(
            ChatTurnModel(
                turn_id=turn_id,
                session_id=session_id,
                stage_id=stage_id,
                user_message_id=user_msg_id,
                expert_message_id=expert_msg_id,
                assistant_message_id=assistant_message_id or expert_msg_id or main_msg_id or user_msg_id,
                rag_record_id=None,
                draft_before=draft_before,
                draft_after=draft_after,
                created_at=main_timestamp,
            )
        )

        sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if sess:
            sess.updated_at = main_timestamp

        db.commit()
        return {
            "user_message_id": user_msg_id,
            "expert_message_id": expert_msg_id,
            "main_message_id": main_msg_id,
            "assistant_message_id": assistant_message_id or expert_msg_id or main_msg_id,
            "assistant_message_type": assistant_message_type,
            "assistant_message_agent_id": assistant_message_agent_id,
        }
    finally:
        db.close()


def apply_stage_action(session_id: str, payload: ChatRequest) -> dict:
    db = SessionLocal()
    try:
        sess, flow, stage, stage_output = get_current_context(db, session_id)
        action = payload.action or "intro"

        if action in {"next_stage", "confirm_stage"}:
            if stage_output and payload.final_content is not None:
                stage_output.final_content = payload.final_content
                stage_output.confirmed = 1
                stage_output.updated_at = now_iso()

            sess.current_stage_index += 1
            if sess.current_stage_index >= len(flow["stages"]):
                sess.status = "completed"
                sess.updated_at = now_iso()
                db.commit()
                return {
                    "completed": True,
                    "message": "全部阶段已完成，可以导出教案。",
                    "stage": None,
                    "flow": flow,
                }
            stage = flow["stages"][sess.current_stage_index]

        elif action == "prev_stage":
            sess.current_stage_index = max(0, sess.current_stage_index - 1)
            sess.status = "active"
            stage = flow["stages"][sess.current_stage_index]

        elif action != "intro":
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

        sess.updated_at = now_iso()
        db.commit()
        return {
            "completed": False,
            "message": PromptService.opening_message(sess.topic, flow["display_name"], stage),
            "stage": stage,
            "flow": flow,
            "topic": sess.topic,
        }
    finally:
        db.close()


@router.post("/{session_id}/chat")
async def chat(session_id: str, payload: ChatRequest, db: Session = Depends(get_db)):
    sess, flow, stage, stage_output = get_current_context(db, session_id)

    if payload.type == "sys_action":
        action_result = apply_stage_action(session_id, payload)

        async def action_events():
            yield format_sse(
                "stage",
                {
                    "stage": action_result["stage"],
                    "completed": action_result["completed"],
                },
            )
            text = action_result["message"]
            if text:
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": "main_agent",
                        "agent_name": "主教学导师",
                        "message_type": "main_tutor",
                    },
                )
            yield format_sse(
                "done",
                {
                    "message_id": None,
                    "completed": action_result["completed"],
                    "degraded": False,
                },
            )

        return StreamingResponse(action_events(), media_type="text/event-stream")

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    all_messages = ContextService.load_messages(db, session_id)
    dialog_history = ContextService.format_dialog_history(all_messages)
    llm_history = ContextService.to_llm_history(all_messages)
    current_draft = stage_output.draft_content if stage_output else ""
    doc_input = ContextService.build_doc_input(db, session_id, stage["id"])
    stage_agent_id = stage["agent_id"]
    stage_agent = DifyAgentService.find_agent(stage_agent_id, sess.flow_name)
    conversation_id = get_agent_conversation_id(db, session_id, stage_agent_id)
    chat_mode = get_global_chat_mode(db)

    session_snapshot = {
        "session_id": sess.id,
        "topic": sess.topic,
        "flow_name": sess.flow_name,
        "flow_display_name": flow["display_name"],
        "stage": stage,
        "current_draft": current_draft,
        "dialog_history": dialog_history,
        "llm_history": llm_history,
        "doc_input": doc_input,
    }

    async def chat_events():
        expert_text = ""
        main_text = ""
        last_draft = ""
        next_conversation_id = conversation_id

        yield format_sse(
            "stage",
            {
                "stage": session_snapshot["stage"],
                "flow_name": session_snapshot["flow_name"],
                "flow_display_name": session_snapshot["flow_display_name"],
                "chat_mode": chat_mode,
            },
        )
        if chat_mode == SUBAGENT_MODE:
            yield format_sse(
                "agent",
                {
                    "mode": "subagent",
                    "agent_id": stage_agent_id,
                    "agent_name": stage["expert"],
                    "message_type": "stage_expert",
                },
            )

            if not stage_agent:
                raise DifyAgentError(f"当前流程未配置阶段专家 {stage_agent_id}")
            async for item in DifyAgentService.chat_stream(
                agent=stage_agent,
                session_id=session_id,
                conversation_id=conversation_id,
                flow_display_name=session_snapshot["flow_display_name"],
                topic=session_snapshot["topic"],
                stage=session_snapshot["stage"],
                message=payload.message,
                dialog_history=session_snapshot["dialog_history"],
                doc_input=session_snapshot["doc_input"],
                current_draft=session_snapshot["current_draft"],
            ):
                text = item.get("text", "")
                next_conversation_id = item.get("conversation_id") or next_conversation_id
                if not text:
                    continue
                expert_text += text
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": stage_agent.id,
                        "agent_name": stage_agent.name,
                        "message_type": "stage_expert",
                    },
                )
            upsert_agent_conversation_id(session_id, stage_agent.id, next_conversation_id)
        else:
            yield format_sse(
                "agent",
                {
                    "mode": "main",
                    "agent_id": "main_agent",
                    "agent_name": "主教学导师",
                    "message_type": "main_tutor",
                },
            )
            system_prompt = PromptService.build_main_agent_prompt(
                topic=session_snapshot["topic"],
                flow_display_name=session_snapshot["flow_display_name"],
                stage=session_snapshot["stage"],
                expert_output="",
                dialog_history=session_snapshot["dialog_history"],
                doc_input=session_snapshot["doc_input"],
                current_draft=session_snapshot["current_draft"],
                expert_degraded=False,
            )
            async for text in LLMService.chat_stream(
                system_prompt,
                session_snapshot["llm_history"],
                payload.message,
            ):
                main_text += text
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": "main_agent",
                        "agent_name": "主教学导师",
                        "message_type": "main_tutor",
                    },
                )
                draft = DraftService.extract_draft(main_text)
                if draft and draft != last_draft:
                    last_draft = draft
                    yield format_sse(
                        "draft",
                        {
                            "content": draft,
                            "agent_id": "main_agent",
                            "message_type": "main_tutor",
                        },
                    )

        final_draft = DraftService.extract_draft(main_text)
        message_ids = save_chat_result(
            session_id=session_id,
            stage_id=stage["id"],
            user_message=payload.message,
            expert_message=expert_text,
            expert_agent_id=stage_agent_id,
            main_message=main_text,
            draft_content=final_draft,
        )
        yield format_sse(
            "done",
            {
                **message_ids,
                "message_id": message_ids["assistant_message_id"],
                "draft_updated": bool(final_draft),
                "conversation_id": next_conversation_id if expert_text else None,
                "degraded": False,
                "failed_agent_id": None,
                "warning": None,
                "chat_mode": chat_mode,
            },
        )

    return StreamingResponse(
        chat_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

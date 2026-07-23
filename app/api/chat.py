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
from app.services.draft_edit_service import DraftEditService
from app.services.draft_generate_service import DraftGenerateService
from app.services.draft_service import DraftService
from app.services.draft_proposal_service import DraftProposalService
from app.services.draft_target_resolver import DraftTarget, DraftTargetResolver
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
    draft_message: str = "",
    draft_agent_id: str = "draft_agent",
    draft_content: str = "",
    update_stage_output: bool = False,
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
        draft_msg_id = None
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

        if draft_message:
            draft_msg_id = new_id("msg")
            assistant_message_id = draft_msg_id
            assistant_message_type = "draft_tutor"
            assistant_message_agent_id = draft_agent_id
            db.add(
                MessageModel(
                    id=draft_msg_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    role="assistant",
                    content=DraftService.strip_draft_markers(draft_message),
                    agent_id=draft_agent_id,
                    message_type="draft_tutor",
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
        if output and draft_content and update_stage_output:
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
            "draft_message_id": draft_msg_id,
            "assistant_message_id": assistant_message_id or expert_msg_id or main_msg_id,
            "assistant_message_type": assistant_message_type,
            "assistant_message_agent_id": assistant_message_agent_id,
        }
    finally:
        db.close()


def target_to_meta_range(target: DraftTarget) -> dict:
    return {
        "start_offset": target.start_offset,
        "end_offset": target.end_offset,
    }


def get_selection_text(payload: ChatRequest) -> str:
    if not payload.selection:
        return ""
    return (payload.selection.selected_text or "").strip()


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
        "draft_mode_enabled": bool(sess.draft_mode_enabled),
        "dialog_history": dialog_history,
        "llm_history": llm_history,
        "doc_input": doc_input,
        "selection_text": get_selection_text(payload),
    }

    async def chat_events():
        expert_text = ""
        main_text = ""
        draft_text = ""
        next_conversation_id = conversation_id
        final_draft = current_draft
        draft_updated = False
        draft_failed = False
        persist_draft_directly = False
        proposal_payload = None
        draft_status_text = ""
        proposal_kind = None
        draft_request_kind = payload.draft_request_kind or (
            "generate" if not session_snapshot["current_draft"].strip() else "edit"
        )

        yield format_sse(
            "stage",
            {
                "stage": session_snapshot["stage"],
                "flow_name": session_snapshot["flow_name"],
                "flow_display_name": session_snapshot["flow_display_name"],
                "chat_mode": chat_mode,
                "draft_mode_enabled": session_snapshot["draft_mode_enabled"],
            },
        )
        if session_snapshot["draft_mode_enabled"]:
            draft_status_text = "我先根据您的想法整理右侧草案，您稍等一下。"
            yield format_sse(
                "agent",
                {
                    "mode": "main",
                    "agent_id": "main_agent",
                    "agent_name": "流程引导Agent",
                    "message_type": "main_tutor",
                },
            )
            yield format_sse(
                "status",
                {
                    "phase": "draft",
                    "state": "start",
                    "text": draft_status_text,
                },
            )
            try:
                DraftProposalService.reject_pending_proposals(
                    db,
                    session_id=session_id,
                    stage_id=stage["id"],
                )
                db.commit()
                if draft_request_kind == "generate":
                    async for candidate_content, chunk in DraftGenerateService.stream_candidate(
                        topic=session_snapshot["topic"],
                        flow_display_name=session_snapshot["flow_display_name"],
                        stage=session_snapshot["stage"],
                        dialog_history=session_snapshot["dialog_history"],
                        doc_input=session_snapshot["doc_input"],
                        current_draft=session_snapshot["current_draft"],
                        user_message=payload.message,
                        llm_history=session_snapshot["llm_history"],
                    ):
                        draft_text = candidate_content
                        yield format_sse(
                            "draft",
                            {
                                "text": chunk,
                                "content": draft_text,
                                "agent_id": "draft_agent",
                                "agent_name": "草案转写Agent",
                                "message_type": "draft_tutor",
                            },
                        )
                    if draft_text and draft_text != session_snapshot["current_draft"]:
                        if not session_snapshot["current_draft"].strip():
                            proposal_kind = "generate"
                            draft_updated = True
                            persist_draft_directly = True
                            final_draft = draft_text
                            draft_status_text = "右侧草案已经整理好了，已直接写入草案。"
                        else:
                            proposal = DraftProposalService.create_proposal(
                                db,
                                session_id=session_id,
                                stage_id=stage["id"],
                                base_content=session_snapshot["current_draft"],
                                candidate_content=draft_text,
                                meta={
                                    "proposal_kind": "generate",
                                    "target_mode": None,
                                    "target_summary": None,
                                    "target_range": None,
                                },
                            )
                            if proposal:
                                db.commit()
                                db.refresh(proposal)
                                proposal_payload = DraftProposalService.serialize(proposal)
                                proposal_kind = "generate"
                                final_draft = draft_text
                                draft_updated = True
                                draft_status_text = "右侧草案已经整理好了，老师可以直接审阅或继续修改。"
                                yield format_sse("proposal", {"proposal": proposal_payload})
                            else:
                                proposal_kind = "generate"
                                draft_status_text = "我刚刚对照检查过，右侧草案暂时不需要调整。"
                    else:
                        proposal_kind = "generate"
                        draft_status_text = "我刚刚对照检查过，右侧草案暂时不需要调整。"
                else:
                    if not payload.selection or not get_selection_text(payload):
                        draft_failed = True
                        proposal_kind = "edit"
                        draft_status_text = "请先选中右侧草案中需要修改的内容，我再继续编辑。"
                        yield format_sse(
                            "status",
                            {
                                "phase": "draft",
                                "state": "error",
                                "text": draft_status_text,
                            },
                        )
                        yield format_sse(
                            "warning",
                            {
                                "agent_id": "draft_agent",
                                "agent_name": "草案编辑Agent",
                                "message": draft_status_text,
                            },
                        )
                        return
                    target = DraftTargetResolver.resolve(
                        current_draft=session_snapshot["current_draft"],
                        selection=(
                            payload.selection.model_dump()
                            if hasattr(payload.selection, "model_dump")
                            else payload.selection.dict()
                        )
                        if payload.selection
                        else None,
                    )
                    if not target:
                        draft_failed = True
                        proposal_kind = "edit"
                        draft_status_text = "我还没有定位到要修改的内容，您可以先选中右侧相关段落再试。"
                    else:
                        draft_status_text = "我先按您选中的这段来调整右侧草案。"
                        yield format_sse(
                            "status",
                            {
                                "phase": "draft",
                                "state": "start",
                                "text": draft_status_text,
                            },
                        )
                        async for candidate_content, _replacement, chunk in DraftEditService.stream_candidate(
                            topic=session_snapshot["topic"],
                            flow_display_name=session_snapshot["flow_display_name"],
                            stage=session_snapshot["stage"],
                            dialog_history=session_snapshot["dialog_history"],
                            doc_input=session_snapshot["doc_input"],
                            current_draft=session_snapshot["current_draft"],
                            user_message=payload.message,
                            llm_history=session_snapshot["llm_history"],
                            target=target,
                        ):
                            draft_text = candidate_content
                            yield format_sse(
                                "draft",
                                {
                                    "text": chunk,
                                    "content": draft_text,
                                    "agent_id": "draft_agent",
                                    "agent_name": "草案编辑Agent",
                                    "message_type": "draft_tutor",
                                },
                            )
                        proposal = DraftProposalService.create_proposal(
                            db,
                            session_id=session_id,
                            stage_id=stage["id"],
                            base_content=session_snapshot["current_draft"],
                            candidate_content=draft_text,
                            meta={
                                "proposal_kind": "edit",
                                "target_mode": target.mode,
                                "target_summary": target.target_summary,
                                "target_range": target_to_meta_range(target),
                            },
                        )
                        if proposal:
                            db.commit()
                            db.refresh(proposal)
                            proposal_payload = DraftProposalService.serialize(proposal)
                            proposal_kind = "edit"
                            final_draft = draft_text
                            draft_updated = True
                            draft_status_text = "右侧草案已经整理好了，老师可以直接审阅或继续修改。"
                            yield format_sse("proposal", {"proposal": proposal_payload})
                        else:
                            proposal_kind = "edit"
                            draft_status_text = "我刚刚对照检查过，右侧草案暂时不需要调整。"
            except Exception:
                draft_failed = True
                draft_status_text = "这次草案整理没有成功，右侧仍保留原草案，我们可以换个说法再试。"
            yield format_sse(
                "status",
                {
                    "phase": "draft",
                    "state": "done" if not draft_failed else "error",
                    "text": draft_status_text,
                },
            )
            if draft_failed:
                main_text = draft_status_text
            else:
                main_text = draft_status_text
                if not draft_updated and draft_text and draft_text == session_snapshot["current_draft"]:
                    final_draft = session_snapshot["current_draft"]
                elif not draft_updated:
                    final_draft = session_snapshot["current_draft"]
        elif chat_mode == SUBAGENT_MODE:
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
                selection_text=session_snapshot["selection_text"],
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
                    "agent_name": "流程引导Agent",
                    "message_type": "main_tutor",
                },
            )
            yield format_sse(
                "status",
                {
                    "phase": "guide",
                    "state": "start",
                    "text": "正在生成流程引导...",
                },
            )
            guide_prompt = PromptService.build_guide_agent_prompt(
                topic=session_snapshot["topic"],
                flow_display_name=session_snapshot["flow_display_name"],
                stage=session_snapshot["stage"],
                dialog_history=session_snapshot["dialog_history"],
                doc_input=session_snapshot["doc_input"],
                current_draft=session_snapshot["current_draft"],
                user_message=payload.message,
                selection_text=session_snapshot["selection_text"],
            )
            async for text in LLMService.chat_stream(
                guide_prompt,
                session_snapshot["llm_history"],
                payload.message,
                response_kind="guide",
            ):
                main_text += text
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": "main_agent",
                        "agent_name": "流程引导Agent",
                        "message_type": "main_tutor",
                    },
                )
            yield format_sse(
                "status",
                {
                    "phase": "guide",
                    "state": "done",
                    "text": "流程引导完成",
                },
            )

        message_ids = save_chat_result(
            session_id=session_id,
            stage_id=stage["id"],
            user_message=payload.message,
            expert_message=expert_text,
            expert_agent_id=stage_agent_id,
            main_message=main_text,
            draft_message="",
            draft_agent_id="draft_agent",
            draft_content=final_draft if session_snapshot["draft_mode_enabled"] else "",
            update_stage_output=persist_draft_directly,
        )
        yield format_sse(
            "done",
            {
                **message_ids,
                "message_id": message_ids["assistant_message_id"],
                "draft_updated": draft_updated,
                "draft_proposal": proposal_payload,
                "draft_failed": draft_failed,
                "draft_status_text": draft_status_text,
                "draft_request_kind": draft_request_kind,
                "proposal_kind": proposal_kind,
                "conversation_id": next_conversation_id if expert_text else None,
                "degraded": False,
                "failed_agent_id": None,
                "warning": None,
                "chat_mode": chat_mode,
                "draft_mode_enabled": session_snapshot["draft_mode_enabled"],
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

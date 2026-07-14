import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    AgentConversationModel,
    ChatTurnModel,
    MessageModel,
    SessionModel,
    StageOutputModel,
    RagRecordModel,
)
from app.schemas import (
    ConfirmStageRequest,
    DraftUpdateRequest,
    RollbackRequest,
    SelectFlowRequest,
    SessionCreate,
)
from app.services.dify_agent_service import DifyAgentService
from app.workflow.flows import get_flow, get_stage


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def create_stage_outputs(db: Session, session_id: str, flow_name: str) -> None:
    flow = get_flow(flow_name)
    timestamp = now_iso()
    for index, stage in enumerate(flow["stages"]):
        db.add(
            StageOutputModel(
                id=new_id("out"),
                session_id=session_id,
                flow_name=flow_name,
                stage_id=stage["id"],
                stage_name=stage["name"],
                order_index=index,
                draft_content="",
                final_content="",
                confirmed=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )


def serialize_session(sess: SessionModel, db: Session) -> dict:
    flow = get_flow(sess.flow_name)
    current_stage = None
    if sess.current_stage_index < len(flow["stages"]):
        current_stage = get_stage(sess.flow_name, sess.current_stage_index)

    outputs = (
        db.query(StageOutputModel)
        .filter(StageOutputModel.session_id == sess.id)
        .order_by(StageOutputModel.order_index.asc())
        .all()
    )
    return {
        "id": sess.id,
        "title": sess.title,
        "topic": sess.topic,
        "flow_name": sess.flow_name,
        "flow_display_name": flow["display_name"],
        "current_stage_index": sess.current_stage_index,
        "current_stage": current_stage,
        "status": sess.status,
        "outputs": [
            {
                "stage_id": item.stage_id,
                "stage_name": item.stage_name,
                "order_index": item.order_index,
                "draft_content": item.draft_content or "",
                "final_content": item.final_content or "",
                "confirmed": bool(item.confirmed),
            }
            for item in outputs
        ],
    }


@router.post("")
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    try:
        flow = get_flow(payload.flow_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    timestamp = now_iso()
    session_id = new_id("sess")
    sess = SessionModel(
        id=session_id,
        title=f"{payload.topic}-探究式教案",
        topic=payload.topic,
        flow_name=payload.flow_name,
        current_stage_index=0,
        status="active",
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(sess)
    create_stage_outputs(db, session_id, payload.flow_name)
    db.commit()
    return {
        "code": 0,
        "message": "success",
        "data": {
            **serialize_session(sess, db),
            "flow": {
                "name": flow["name"],
                "display_name": flow["display_name"],
                "stage_count": len(flow["stages"]),
            },
        },
    }


@router.get("")
def list_sessions(db: Session = Depends(get_db), limit: int = 20):
    sessions = (
        db.query(SessionModel)
        .order_by(SessionModel.updated_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    data = []
    for sess in sessions:
        flow = get_flow(sess.flow_name)
        data.append(
            {
                "id": sess.id,
                "title": sess.title,
                "topic": sess.topic,
                "flow_name": sess.flow_name,
                "flow_display_name": flow["display_name"],
                "current_stage_index": sess.current_stage_index,
                "status": sess.status,
                "updated_at": sess.updated_at,
                "created_at": sess.created_at,
            }
        )
    return {"code": 0, "message": "success", "data": data}


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"code": 0, "message": "success", "data": serialize_session(sess, db)}


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Cascade delete all related data to keep DB clean
    db.query(StageOutputModel).filter(StageOutputModel.session_id == session_id).delete()
    db.query(AgentConversationModel).filter(AgentConversationModel.session_id == session_id).delete()
    db.query(MessageModel).filter(MessageModel.session_id == session_id).delete()
    db.query(ChatTurnModel).filter(ChatTurnModel.session_id == session_id).delete()
    db.query(RagRecordModel).filter(RagRecordModel.session_id == session_id).delete()
    
    db.delete(sess)
    db.commit()
    return {"code": 0, "message": "session deleted successfully"}


@router.get("/{session_id}/messages")
def get_messages(session_id: str, db: Session = Depends(get_db)):
    messages = (
        db.query(MessageModel)
        .filter(MessageModel.session_id == session_id)
        .order_by(MessageModel.created_at.asc())
        .all()
    )
    return {
        "code": 0,
        "message": "success",
        "data": [
            {
                "id": item.id,
                "stage_id": item.stage_id,
                "role": item.role,
                "content": item.content,
                "agent_id": item.agent_id,
                "message_type": item.message_type,
                "created_at": item.created_at,
            }
            for item in messages
        ],
    }


@router.post("/{session_id}/select_flow")
def select_flow(session_id: str, payload: SelectFlowRequest, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        get_flow(payload.flow_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    db.query(StageOutputModel).filter(StageOutputModel.session_id == session_id).delete()
    db.query(AgentConversationModel).filter(AgentConversationModel.session_id == session_id).delete()
    db.query(ChatTurnModel).filter(ChatTurnModel.session_id == session_id).delete()
    db.query(RagRecordModel).filter(RagRecordModel.session_id == session_id).delete()
    if payload.clear_messages:
        db.query(MessageModel).filter(MessageModel.session_id == session_id).delete()

    sess.flow_name = payload.flow_name
    sess.current_stage_index = 0
    sess.status = "active"
    sess.updated_at = now_iso()
    create_stage_outputs(db, session_id, payload.flow_name)
    db.commit()
    db.refresh(sess)
    return {"code": 0, "message": "flow selected", "data": serialize_session(sess, db)}


@router.post("/{session_id}/confirm-stage")
def confirm_stage(session_id: str, payload: ConfirmStageRequest, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    flow = get_flow(sess.flow_name)
    if sess.current_stage_index >= len(flow["stages"]):
        raise HTTPException(status_code=400, detail="Workflow already completed")

    stage = flow["stages"][sess.current_stage_index]
    output = (
        db.query(StageOutputModel)
        .filter(StageOutputModel.session_id == session_id, StageOutputModel.stage_id == stage["id"])
        .first()
    )
    if output:
        output.final_content = payload.final_content
        output.confirmed = 1
        output.updated_at = now_iso()

    sess.current_stage_index += 1
    if sess.current_stage_index >= len(flow["stages"]):
        sess.status = "completed"
    sess.updated_at = now_iso()
    db.commit()
    db.refresh(sess)
    return {"code": 0, "message": "stage confirmed", "data": serialize_session(sess, db)}


@router.post("/{session_id}/rollback")
def rollback(session_id: str, payload: RollbackRequest, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if payload.stage_back:
        sess.current_stage_index = max(0, sess.current_stage_index - 1)
        sess.status = "active"
        stage = get_stage(sess.flow_name, sess.current_stage_index)
        output = (
            db.query(StageOutputModel)
            .filter(StageOutputModel.session_id == session_id, StageOutputModel.stage_id == stage["id"])
            .first()
        )
        if output:
            output.confirmed = 0
            output.final_content = ""
            output.updated_at = now_iso()
        deleted_ids = []
        restored_drafts = {}
    else:
        turns = (
            db.query(ChatTurnModel)
            .filter(ChatTurnModel.session_id == session_id)
            .order_by(ChatTurnModel.id.desc())
            .limit(payload.steps)
            .all()
        )
        deleted_ids = []
        restored_drafts = {}

        if turns:
            oldest_turn_by_stage = {}
            for turn in turns:
                turn_message_ids = [
                    turn.user_message_id,
                    turn.expert_message_id,
                    turn.assistant_message_id,
                ]
                turn_message_ids = [message_id for message_id in turn_message_ids if message_id]
                deleted_ids.extend(turn_message_ids)
                oldest_turn_by_stage[turn.stage_id] = turn
                if turn.rag_record_id:
                    db.query(RagRecordModel).filter(RagRecordModel.id == turn.rag_record_id).delete()
                db.query(MessageModel).filter(
                    MessageModel.id.in_(turn_message_ids)
                ).delete(synchronize_session=False)
                db.delete(turn)

            for stage_id, turn in oldest_turn_by_stage.items():
                output = (
                    db.query(StageOutputModel)
                    .filter(
                        StageOutputModel.session_id == session_id,
                        StageOutputModel.stage_id == stage_id,
                    )
                    .first()
                )
                if output:
                    output.draft_content = turn.draft_before or ""
                    output.updated_at = now_iso()
                    restored_drafts[stage_id] = output.draft_content
        else:
            # Compatibility fallback for conversations created before Day 3 turn tracking.
            legacy_messages = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.created_at.desc())
                .limit(payload.steps * 3)
                .all()
            )
            deleted_ids = [item.id for item in legacy_messages]
            for item in legacy_messages:
                db.delete(item)

    sess.updated_at = now_iso()
    db.commit()
    db.refresh(sess)
    return {
        "code": 0,
        "message": "rollback completed",
        "data": {
            "deleted_message_ids": deleted_ids,
            "restored_drafts": restored_drafts,
            "session": serialize_session(sess, db),
        },
    }


@router.put("/{session_id}/stages/{stage_id}/draft")
def update_stage_draft(
    session_id: str,
    stage_id: str,
    payload: DraftUpdateRequest,
    db: Session = Depends(get_db),
):
    output = (
        db.query(StageOutputModel)
        .filter(StageOutputModel.session_id == session_id, StageOutputModel.stage_id == stage_id)
        .first()
    )
    if not output:
        raise HTTPException(status_code=404, detail="Stage output not found")
    output.draft_content = payload.draft_content
    output.updated_at = now_iso()
    db.commit()
    return {
        "code": 0,
        "message": "draft saved",
        "data": {"stage_id": stage_id, "draft_content": output.draft_content},
    }


@router.get("/{session_id}/dify_agents")
def get_dify_agents(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    agents = DifyAgentService.list_agents(sess.flow_name)
    return {
        "code": 0,
        "message": "success",
        "data": [
            {
                "id": agent.id,
                "stage_id": agent.stage_id,
                "command": agent.command,
                "name": agent.name,
                "description": agent.description,
                "flow_names": list(agent.flow_names),
                "configured": bool(agent.api_url and agent.api_key),
            }
            for agent in agents
        ],
    }

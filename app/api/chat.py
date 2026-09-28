import asyncio
import contextlib
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.registry import get_agent_registry
from app.agents.service import ExpertAgentService
from app.core.auth import get_current_user
from app.core.sse import format_sse
from app.db.database import SessionLocal, get_db
from app.db.models import (
    ChatTurnModel,
    MessageModel,
    RagRecordModel,
    SessionModel,
    StageOutputModel,
    UserModel,
)
from app.schemas import ChatRequest
from app.services.context_service import ContextService
from app.services.chat_interrupt_service import ChatInterrupted, chat_interruptions
from app.services.curriculum_permission_service import CurriculumPermissionService
from app.services.draft_edit_service import DraftEditService
from app.services.draft_generate_service import DraftGenerateService
from app.services.draft_service import DraftService
from app.services.draft_proposal_service import DraftProposalService
from app.services.draft_target_resolver import DraftTarget, DraftTargetResolver
from app.services.graph_rag_service import GraphRagService
from app.services.globi_runtime_service import (
    GlobiRuntimeService,
    RUNTIME_ENTITY_PREFIX,
    RUNTIME_PATH_PREFIX,
    RUNTIME_RELATION_PREFIX,
    SUPPORTED_EXPERTS,
)
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.rag_service import RagService
from app.services.session_access_service import get_owned_session
from app.workflow.flows import get_flow


router = APIRouter(prefix="/api/sessions", tags=["chat"])


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def get_current_context(
    db: Session,
    session_id: str,
    user_id: str,
) -> tuple[SessionModel, dict, dict, StageOutputModel | None]:
    sess = get_owned_session(db, session_id, user_id)

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


def save_chat_result(
    *,
    session_id: str,
    stage_id: str,
    user_message: str,
    expert_message: str = "",
    expert_agent_id: str,
    main_message: str = "",
    draft_message: str = "",
    draft_content: str = "",
    update_stage_output: bool = False,
    rag_record: dict | None = None,
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
                    message_type="expert_advice",
                    created_at=now_iso(),
                )
            )

        assistant_message_id = expert_msg_id
        assistant_message_type = "expert_advice"
        assistant_message_agent_id = expert_agent_id
        main_timestamp = now_iso()
        draft_msg_id = None
        if main_message:
            main_msg_id = new_id("msg")
            assistant_message_id = main_msg_id
            assistant_message_type = "main_tutor"
            assistant_message_agent_id = "main_tutor"
            db.add(
                MessageModel(
                    id=main_msg_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    role="assistant",
                    content=DraftService.strip_draft_markers(main_message),
                    agent_id="main_tutor",
                    message_type="main_tutor",
                    created_at=main_timestamp,
                )
            )

        if draft_message:
            draft_msg_id = new_id("msg")
            assistant_message_id = draft_msg_id
            assistant_message_type = "main_tutor"
            assistant_message_agent_id = "main_tutor"
            db.add(
                MessageModel(
                    id=draft_msg_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    role="assistant",
                    content=DraftService.strip_draft_markers(draft_message),
                    agent_id="main_tutor",
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
        if output and draft_content and update_stage_output:
            output.draft_content = draft_content
            output.updated_at = main_timestamp

        rag_record_id = None
        if rag_record is not None:
            rag_record_id = new_id("rag")
            db.add(
                RagRecordModel(
                    id=rag_record_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    query=rag_record.get("query", ""),
                    context=rag_record.get("context", ""),
                    source_json=RagService.source_json(rag_record.get("source", {})),
                    created_at=main_timestamp,
                )
            )

        db.add(
            ChatTurnModel(
                turn_id=turn_id,
                session_id=session_id,
                stage_id=stage_id,
                user_message_id=user_msg_id,
                expert_message_id=expert_msg_id,
                assistant_message_id=assistant_message_id or expert_msg_id or main_msg_id or user_msg_id,
                rag_record_id=rag_record_id,
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
            "rag_record_id": rag_record_id,
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


def apply_stage_action(session_id: str, payload: ChatRequest, user_id: str) -> dict:
    db = SessionLocal()
    try:
        sess, flow, stage, stage_output = get_current_context(db, session_id, user_id)
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
async def chat(
    session_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    sess, flow, stage, stage_output = get_current_context(db, session_id, user.id)
    request_id = payload.request_id or new_id("chat")

    if payload.type == "sys_action":
        try:
            chat_interruptions.register(request_id, session_id, user.id)
            action_result = apply_stage_action(session_id, payload, user.id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        async def action_events():
            chat_interruptions.bind_current_task(request_id)
            try:
                if chat_interruptions.is_cancelled(request_id):
                    raise ChatInterrupted()
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
                            "agent_id": "main_tutor",
                            "agent_name": "主导师 Agent",
                            "agent_role": "探究教学主导师",
                            "message_type": "main_tutor",
                        },
                    )
                yield format_sse(
                    "done",
                    {
                        "message_id": None,
                        "completed": action_result["completed"],
                        "degraded": False,
                        "agent_id": "main_tutor",
                        "agent_name": "主导师 Agent",
                        "agent_role": "探究教学主导师",
                        "message_type": "main_tutor",
                        "request_id": request_id,
                    },
                )
            except ChatInterrupted:
                yield format_sse(
                    "interrupted",
                    {
                        "request_id": request_id,
                        "agent_id": "main_tutor",
                        "agent_name": "主导师 Agent",
                        "agent_role": "探究教学主导师",
                        "message_type": "main_tutor",
                    },
                )
            except asyncio.CancelledError:
                raise
            finally:
                chat_interruptions.unregister(request_id)

        return StreamingResponse(action_events(), media_type="text/event-stream")

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    registry = get_agent_registry()
    selected_expert = None
    if payload.expert_id:
        selected_expert = registry.selectable_expert(payload.expert_id)
        if selected_expert is None:
            raise HTTPException(status_code=400, detail="未知或不可选择的专家 Agent")

    all_messages = ContextService.load_messages(db, session_id)
    dialog_history = ContextService.format_dialog_history(all_messages)
    llm_history = ContextService.to_llm_history(all_messages)
    current_draft = stage_output.draft_content if stage_output else ""
    base_doc_input = ContextService.build_doc_input(db, session_id, stage["id"])
    curriculum_context = ""
    curriculum_source: dict = {}
    local_graph_context = ""
    runtime_graph_context = ""
    graph_source: dict = {}
    graph_warning = ""
    graph_payload: dict | None = None
    allowed_sources: list[str] = []
    if selected_expert is not None:
        allowed_sources = CurriculumPermissionService.allowed_sources(db, selected_expert.id)
        if allowed_sources and payload.graph_selection is None:
            curriculum_context, curriculum_source = RagService.retrieve_curriculum_context(
                db,
                topic=sess.topic,
                stage=stage,
                user_message=payload.message,
                expert_id=selected_expert.id,
                allowed_sources=allowed_sources,
            )
    graph_service = KnowledgeGraphService(db)
    runtime_service = GlobiRuntimeService(db)
    is_runtime_graph_expert = bool(
        selected_expert is not None and selected_expert.id in SUPPORTED_EXPERTS
    )
    local_candidate: dict | None = None
    runtime_candidate: dict | None = None
    runtime_query_required = False
    if is_runtime_graph_expert:
        local_candidate = graph_service.find_candidate_graph(
            message=payload.message,
            expert_id=selected_expert.id,
            topic=sess.topic,
            stage=stage,
        )
        query_id = (
            payload.graph_selection.globi_query_id
            if payload.graph_selection is not None
            else None
        )
        if query_id:
            runtime_candidate, snapshot_warning = runtime_service.snapshot_payload(
                query_id=query_id,
                user_id=user.id,
                session_id=sess.id,
            )
            if snapshot_warning:
                graph_warning = snapshot_warning
        else:
            # Run the network lookup inside the SSE generator so the client can
            # receive real progress before GloBI finishes.
            runtime_query_required = True
        if runtime_candidate is None and not runtime_query_required:
            runtime_candidate = runtime_service.empty_payload(
                status="expired",
                warning=graph_warning,
            )
        if runtime_candidate is not None:
            graph_payload = runtime_service.merge_graphs(local_candidate, runtime_candidate)

    if payload.graph_selection is not None:
        graph_selection = payload.graph_selection
        local_entity_ids = [
            row for row in graph_selection.entity_ids
            if not row.startswith(RUNTIME_ENTITY_PREFIX)
        ]
        local_relation_ids = [
            row for row in graph_selection.relation_ids
            if not row.startswith(RUNTIME_RELATION_PREFIX)
        ]
        local_path_ids = [
            row for row in graph_selection.path_ids
            if not row.startswith(RUNTIME_PATH_PREFIX)
        ]
        has_local_selection = bool(local_entity_ids or local_relation_ids or local_path_ids)
        validation = graph_service.validate_selection(
            message=payload.message,
            selected_path_ids=local_path_ids,
            selected_relation_ids=local_relation_ids,
            selected_entity_ids=local_entity_ids,
        ) if has_local_selection else None
        if validation is not None and validation.valid:
            selected_graph = graph_service.selected_graph_payload(
                selected_path_ids=local_path_ids,
                selected_relation_ids=local_relation_ids,
                selected_entity_ids=local_entity_ids,
            )
            local_graph_context = graph_service.format_selected_graph_context(selected_graph)
            graph_rag_context, graph_rag_source = GraphRagService(db).retrieve_for_selection(
                message=payload.message,
                selected_entity_ids=[entity["id"] for entity in selected_graph["entities"]],
                selected_relation_ids=selected_graph["selected_relation_ids"],
                allowed_sources=allowed_sources,
            )
            local_graph_context = RagService.merge_context(local_graph_context, graph_rag_context)
            graph_source = {
                **graph_rag_source,
                "selected_entity_ids": selected_graph["selected_entity_ids"],
                "selected_relation_ids": selected_graph["selected_relation_ids"],
                "selected_path_ids": selected_graph["selected_path_ids"],
                "paths": selected_graph["paths"],
            }
        elif validation is not None:
            graph_warning = validation.warning

        runtime_entity_ids = [
            row for row in graph_selection.entity_ids
            if row.startswith(RUNTIME_ENTITY_PREFIX)
        ]
        runtime_relation_ids = [
            row for row in graph_selection.relation_ids
            if row.startswith(RUNTIME_RELATION_PREFIX)
        ]
        runtime_path_ids = [
            row for row in graph_selection.path_ids
            if row.startswith(RUNTIME_PATH_PREFIX)
        ]
        if runtime_entity_ids or runtime_relation_ids or runtime_path_ids:
            if not graph_selection.globi_query_id:
                graph_warning = "GloBI 临时图谱缺少查询标识，请刷新后重新选择。"
            else:
                selected_runtime, runtime_warning = runtime_service.select_snapshot(
                    query_id=graph_selection.globi_query_id,
                    user_id=user.id,
                    session_id=sess.id,
                    entity_ids=runtime_entity_ids,
                    relation_ids=runtime_relation_ids,
                    path_ids=runtime_path_ids,
                )
                if selected_runtime is not None:
                    runtime_graph_context = runtime_service.format_context(selected_runtime)
                elif runtime_warning:
                    graph_warning = runtime_warning
    elif runtime_candidate is not None:
        runtime_graph_context = runtime_service.format_context(
            runtime_service.default_selection(runtime_candidate)
        )

    graph_context = RagService.merge_context(local_graph_context, runtime_graph_context)
    doc_input = RagService.merge_context(
        RagService.merge_context(base_doc_input, curriculum_context),
        graph_context,
    )
    curriculum_sources = RagService.curriculum_sources(curriculum_source)
    if graph_source.get("hit_sources"):
        curriculum_sources = list(dict.fromkeys([*curriculum_sources, *graph_source["hit_sources"]]))
    rag_source = curriculum_source.copy() if curriculum_source else {}
    if graph_source:
        rag_source["graph"] = graph_source

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
        "rag_record": {
            "query": curriculum_source.get("query", "") or payload.message,
            "context": RagService.merge_context(curriculum_context, local_graph_context),
            "source": rag_source,
        } if rag_source else None,
        "rag_sources": curriculum_sources,
        "allowed_sources": allowed_sources,
        "selection_text": get_selection_text(payload),
        "graph_warning": graph_warning,
        "graph_payload": graph_payload,
    }

    try:
        chat_interruptions.register(request_id, session_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    async def ensure_chat_active() -> None:
        if chat_interruptions.is_cancelled(request_id):
            raise ChatInterrupted()

    async def chat_body():
        expert_text = ""
        main_text = ""
        draft_text = ""
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
        agent_identity = {
            "agent_id": selected_expert.id if selected_expert else "main_tutor",
            "agent_name": selected_expert.name if selected_expert else "主导师 Agent",
            "agent_role": selected_expert.role if selected_expert else "探究教学主导师",
            "message_type": "expert_advice" if selected_expert else "main_tutor",
        }

        await ensure_chat_active()
        yield format_sse(
            "stage",
            {
                **agent_identity,
                "stage": session_snapshot["stage"],
                "flow_name": session_snapshot["flow_name"],
                "flow_display_name": session_snapshot["flow_display_name"],
                "draft_mode_enabled": session_snapshot["draft_mode_enabled"],
            },
        )
        if runtime_query_required:
            progress_queue: asyncio.Queue[dict] = asyncio.Queue()
            yield format_sse(
                "graph_progress",
                {
                    **agent_identity,
                    "phase": "local_ready",
                    "percent": 8,
                    "message": "本地图谱已完成，开始查询 GloBI 全球关系",
                },
            )
            query_task = asyncio.create_task(
                runtime_service.query(
                    message=payload.message,
                    expert_id=selected_expert.id,
                    user_id=user.id,
                    session_id=session_snapshot["session_id"],
                    progress=progress_queue.put,
                )
            )
            try:
                while not query_task.done():
                    await ensure_chat_active()
                    try:
                        progress_event = await asyncio.wait_for(progress_queue.get(), timeout=0.25)
                    except asyncio.TimeoutError:
                        continue
                    yield format_sse("graph_progress", {**agent_identity, **progress_event})
            except BaseException:
                query_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await query_task
                raise
            while not progress_queue.empty():
                yield format_sse(
                    "graph_progress",
                    {**agent_identity, **progress_queue.get_nowait()},
                )
            try:
                completed_runtime = await query_task
            except Exception:
                completed_runtime = runtime_service.empty_payload(
                    status="failed",
                    warning="GloBI 查询暂时不可用，已继续使用本地图谱",
                )
            session_snapshot["graph_payload"] = runtime_service.merge_graphs(
                local_candidate or runtime_service.empty_payload(status="skipped"),
                completed_runtime,
            )
            completed_runtime_context = runtime_service.format_context(
                runtime_service.default_selection(completed_runtime)
            )
            session_snapshot["doc_input"] = RagService.merge_context(
                session_snapshot["doc_input"],
                completed_runtime_context,
            )
        if session_snapshot["graph_payload"] is not None:
            yield format_sse(
                "graph",
                {
                    **agent_identity,
                    "graph": session_snapshot["graph_payload"],
                },
            )
        if session_snapshot["graph_warning"]:
            yield format_sse(
                "warning",
                {
                    **agent_identity,
                    "message": session_snapshot["graph_warning"],
                    "warning_type": "graph_selection",
                },
            )
        if selected_expert is not None:
            yield format_sse(
                "agent",
                {
                    "agent_id": selected_expert.id,
                    "agent_name": selected_expert.name,
                    "agent_role": selected_expert.role,
                    "message_type": "expert_advice",
                },
            )
            expert_prompt = ExpertAgentService.build_prompt(
                agent=selected_expert,
                topic=session_snapshot["topic"],
                flow_display_name=session_snapshot["flow_display_name"],
                stage=session_snapshot["stage"],
                dialog_history=session_snapshot["dialog_history"],
                doc_input=session_snapshot["doc_input"],
                current_draft=session_snapshot["current_draft"],
                user_message=payload.message,
                selection_text=session_snapshot["selection_text"],
            )
            async for text in ExpertAgentService.chat_stream(
                agent=selected_expert,
                system_prompt=expert_prompt,
                message=payload.message,
            ):
                await ensure_chat_active()
                expert_text += text
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": selected_expert.id,
                        "agent_name": selected_expert.name,
                        "agent_role": selected_expert.role,
                        "message_type": "expert_advice",
                    },
                )
        elif session_snapshot["draft_mode_enabled"]:
            draft_status_text = "我先根据您的想法整理右侧草案，您稍等一下。"
            yield format_sse(
                "agent",
                {
                    "agent_id": "main_tutor",
                    "agent_name": "主导师 Agent",
                    "agent_role": "探究教学主导师",
                    "message_type": "main_tutor",
                },
            )
            yield format_sse(
                "status",
                {
                    **agent_identity,
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
                        await ensure_chat_active()
                        draft_text = candidate_content
                        yield format_sse(
                            "draft",
                            {
                                **agent_identity,
                                "text": chunk,
                                "content": draft_text,
                                "agent_id": "main_tutor",
                                "agent_name": "主导师 Agent",
                                "agent_role": "探究教学主导师",
                                "message_type": "main_tutor",
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
                            await ensure_chat_active()
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
                                await ensure_chat_active()
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
                                **agent_identity,
                                "phase": "draft",
                                "state": "error",
                                "text": draft_status_text,
                            },
                        )
                        yield format_sse(
                            "warning",
                            {
                                **agent_identity,
                                "agent_id": "main_tutor",
                                "agent_name": "主导师 Agent",
                                "agent_role": "探究教学主导师",
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
                                **agent_identity,
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
                            await ensure_chat_active()
                            draft_text = candidate_content
                            yield format_sse(
                                "draft",
                                {
                                    **agent_identity,
                                    "text": chunk,
                                    "content": draft_text,
                                    "agent_id": "main_tutor",
                                    "agent_name": "主导师 Agent",
                                    "agent_role": "探究教学主导师",
                                    "message_type": "main_tutor",
                                },
                            )
                        await ensure_chat_active()
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
                            await ensure_chat_active()
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
            except ChatInterrupted:
                raise
            except Exception:
                draft_failed = True
                draft_status_text = "这次草案整理没有成功，右侧仍保留原草案，我们可以换个说法再试。"
            yield format_sse(
                "status",
                {
                    **agent_identity,
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
        else:
            yield format_sse(
                "agent",
                {
                    "agent_id": "main_tutor",
                    "agent_name": "主导师 Agent",
                    "agent_role": "探究教学主导师",
                    "message_type": "main_tutor",
                },
            )
            yield format_sse(
                "status",
                {
                    **agent_identity,
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
                await ensure_chat_active()
                main_text += text
                yield format_sse(
                    "delta",
                    {
                        "text": text,
                        "agent_id": "main_tutor",
                        "agent_name": "主导师 Agent",
                        "agent_role": "探究教学主导师",
                        "message_type": "main_tutor",
                    },
                )
            yield format_sse(
                "status",
                {
                    **agent_identity,
                    "phase": "guide",
                    "state": "done",
                    "text": "流程引导完成",
                },
            )

        await ensure_chat_active()
        source_note = RagService.source_note(session_snapshot["rag_sources"])
        if source_note and selected_expert is not None:
            expert_text += source_note
            yield format_sse(
                "delta",
                {
                    "text": source_note,
                    "agent_id": selected_expert.id,
                    "agent_name": selected_expert.name,
                    "agent_role": selected_expert.role,
                    "message_type": "expert_advice",
                },
            )

        await ensure_chat_active()
        message_ids = save_chat_result(
            session_id=session_id,
            stage_id=stage["id"],
            user_message=payload.message,
            expert_message=expert_text,
            expert_agent_id=selected_expert.id if selected_expert else "",
            main_message=main_text,
            draft_message="",
            draft_content=(
                final_draft
                if selected_expert is None and session_snapshot["draft_mode_enabled"]
                else ""
            ),
            update_stage_output=persist_draft_directly,
            rag_record=session_snapshot["rag_record"],
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
                "degraded": False,
                "warning": None,
                "draft_mode_enabled": session_snapshot["draft_mode_enabled"],
                "rag_sources": session_snapshot["rag_sources"],
                "agent_id": selected_expert.id if selected_expert else "main_tutor",
                "agent_name": selected_expert.name if selected_expert else "主导师 Agent",
                "agent_role": selected_expert.role if selected_expert else "探究教学主导师",
                "message_type": "expert_advice" if selected_expert else "main_tutor",
                "request_id": request_id,
            },
        )

    async def chat_events():
        chat_interruptions.bind_current_task(request_id)
        try:
            async for event in chat_body():
                yield event
        except ChatInterrupted:
            interrupted_agent = selected_expert or get_agent_registry().main_tutor()
            yield format_sse(
                "interrupted",
                {
                    "request_id": request_id,
                    "agent_id": interrupted_agent.id,
                    "agent_name": interrupted_agent.name,
                    "agent_role": interrupted_agent.role,
                    "message_type": "expert_advice" if selected_expert else "main_tutor",
                },
            )
        except asyncio.CancelledError:
            raise
        finally:
            chat_interruptions.unregister(request_id)

    return StreamingResponse(
        chat_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/chat/{request_id}/cancel")
def cancel_chat(
    session_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    get_owned_session(db, session_id, user.id)
    cancelled = chat_interruptions.cancel(request_id, session_id, user.id)
    return {
        "code": 0,
        "message": "chat interrupted" if cancelled else "chat request is no longer active",
        "data": {"request_id": request_id, "cancelled": cancelled},
    }

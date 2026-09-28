import asyncio
import contextlib
import json
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.registry import get_agent_registry
from app.core.auth import get_admin_user, get_current_user
from app.core.sse import format_sse
from app.db.database import get_db
from app.db.models import UserModel
from app.schemas import (
    KnowledgeEntityRagSourcesRequest,
    KnowledgeEntityUpsertRequest,
    KnowledgeRelationUpsertRequest,
)
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.ecology_graph_sync_service import EcologyGraphSyncService
from app.services.globi_import_service import GlobiImportOptions, GlobiImportService
from app.services.globi_runtime_service import GlobiRuntimeService, SUPPORTED_EXPERTS
from app.services.session_access_service import get_owned_session
from app.workflow.flows import get_flow


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class GraphCandidateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(default="")
    expert_id: str | None = Field(default=None, max_length=128)


class EcologyGraphSyncRequest(BaseModel):
    source: str | None = Field(default=None, max_length=1024)
    force: bool = True


def _globi_options(
    include_insect_insect: bool,
    keep_unknown_region: bool,
    batch_size: int,
    interaction_types_json: str,
) -> GlobiImportOptions:
    try:
        interaction_types = json.loads(interaction_types_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("关系类型筛选不是有效 JSON") from exc
    if interaction_types and not isinstance(interaction_types, list):
        raise ValueError("关系类型筛选必须是数组")
    return GlobiImportOptions.from_dict(
        {
            "include_insect_insect": include_insect_insect,
            "keep_unknown_region": keep_unknown_region,
            "batch_size": batch_size,
            "interaction_types": interaction_types or None,
        }
    )


def _stage_globi_upload(file: UploadFile) -> Path:
    target_dir = Path("data/runtime/globi").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    suffixes = "".join(Path(file.filename or "globi.csv").suffixes) or ".csv"
    handle = tempfile.NamedTemporaryFile(
        prefix="globi-upload-",
        suffix=suffixes,
        dir=target_dir,
        delete=False,
    )
    path = Path(handle.name)
    try:
        with handle:
            shutil.copyfileobj(file.file, handle, length=1024 * 1024)
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _raise_graph_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.post("/graph/candidates")
async def graph_candidates(
    payload: GraphCandidateRequest,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    sess = get_owned_session(db, payload.session_id, user.id)
    flow = get_flow(sess.flow_name)
    stage = (
        flow["stages"][sess.current_stage_index]
        if sess.current_stage_index < len(flow["stages"])
        else {}
    )
    if (
        payload.expert_id
        and get_agent_registry().selectable_expert(payload.expert_id) is None
    ):
        raise HTTPException(status_code=400, detail="未知或不可选择的专家 Agent")
    service = KnowledgeGraphService(db)
    local_data = service.find_candidate_graph(
        message=payload.message,
        expert_id=payload.expert_id or "",
        topic=sess.topic,
        stage=stage,
    )
    if (payload.expert_id or "") in SUPPORTED_EXPERTS:
        runtime_data = await GlobiRuntimeService(db).query(
            message=payload.message,
            expert_id=payload.expert_id or "",
            user_id=user.id,
            session_id=sess.id,
        )
        data = GlobiRuntimeService.merge_graphs(local_data, runtime_data)
    else:
        data = local_data
    return {"code": 0, "message": "success", "data": data}


@router.post("/graph/candidates/stream")
async def stream_graph_candidates(
    payload: GraphCandidateRequest,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Stream local/GloBI graph progress for explicit graph refreshes."""
    sess = get_owned_session(db, payload.session_id, user.id)
    flow = get_flow(sess.flow_name)
    stage = (
        flow["stages"][sess.current_stage_index]
        if sess.current_stage_index < len(flow["stages"])
        else {}
    )
    if payload.expert_id and get_agent_registry().selectable_expert(payload.expert_id) is None:
        raise HTTPException(status_code=400, detail="未知或不可选择的专家 Agent")
    local_data = KnowledgeGraphService(db).find_candidate_graph(
        message=payload.message,
        expert_id=payload.expert_id or "",
        topic=sess.topic,
        stage=stage,
    )

    async def events():
        yield format_sse(
            "graph_progress",
            {
                "phase": "local_ready",
                "percent": 8,
                "message": "本地图谱已完成，开始查询 GloBI 全球关系",
            },
        )
        if (payload.expert_id or "") not in SUPPORTED_EXPERTS:
            yield format_sse("graph", {"graph": local_data})
            return
        progress_queue: asyncio.Queue[dict] = asyncio.Queue()
        service = GlobiRuntimeService(db)
        task = asyncio.create_task(
            service.query(
                message=payload.message,
                expert_id=payload.expert_id or "",
                user_id=user.id,
                session_id=sess.id,
                progress=progress_queue.put,
            )
        )
        try:
            while not task.done():
                try:
                    item = await asyncio.wait_for(progress_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                yield format_sse("graph_progress", item)
        except BaseException:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            raise
        while not progress_queue.empty():
            yield format_sse("graph_progress", progress_queue.get_nowait())
        try:
            runtime_data = await task
        except Exception:
            runtime_data = service.empty_payload(
                status="failed",
                warning="GloBI 查询暂时不可用，已继续使用本地图谱",
            )
        yield format_sse("graph", {"graph": service.merge_graphs(local_data, runtime_data)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/graph")
def get_graph_for_admin(
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    data = service.all_graph()
    return {"code": 0, "message": "success", "data": data}


@router.post("/graph/entities")
def create_graph_entity(
    payload: KnowledgeEntityUpsertRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        entity = service.create_entity(**payload.model_dump())
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph entity created", "data": entity}


@router.put("/graph/entities/{entity_id}")
def update_graph_entity(
    entity_id: str,
    payload: KnowledgeEntityUpsertRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        entity = service.update_entity(entity_id, **payload.model_dump())
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph entity updated", "data": entity}


@router.delete("/graph/entities/{entity_id}")
def delete_graph_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        service.delete_entity(entity_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph entity deleted", "data": None}


@router.put("/graph/entities/{entity_id}/rag-sources")
def replace_graph_entity_rag_sources(
    entity_id: str,
    payload: KnowledgeEntityRagSourcesRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        sources = service.replace_rag_sources(entity_id, payload.sources)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {
        "code": 0,
        "message": "graph entity rag sources updated",
        "data": {"entity_id": entity_id, "sources": sources},
    }


@router.post("/graph/relations")
def create_graph_relation(
    payload: KnowledgeRelationUpsertRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        relation = service.create_relation(**payload.model_dump())
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph relation created", "data": relation}


@router.put("/graph/relations/{relation_id}")
def update_graph_relation(
    relation_id: str,
    payload: KnowledgeRelationUpsertRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        relation = service.update_relation(
            relation_id,
            **payload.model_dump(),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph relation updated", "data": relation}


@router.delete("/graph/relations/{relation_id}")
def delete_graph_relation(
    relation_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        service.delete_relation(relation_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "graph relation deleted", "data": None}


@router.post("/graph/relations/{relation_id}/restore-auto")
def restore_auto_graph_relation(
    relation_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        relation = KnowledgeGraphService(db).restore_auto_relation(relation_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {
        "code": 0,
        "message": "automatic graph relation restored",
        "data": relation,
    }


@router.post("/ecology-graph/sync")
def start_ecology_graph_sync(
    payload: EcologyGraphSyncRequest,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = EcologyGraphSyncService(db)
    try:
        if payload.source:
            job = service.enqueue_source(payload.source, force=payload.force)
            if job is None:
                raise ValueError("指定来源不存在，或不属于生态资料")
            jobs = [job]
        else:
            jobs = service.enqueue_all(force=payload.force)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {
        "code": 0,
        "message": "ecology graph sync queued",
        "data": {"jobs": jobs, "queued_count": len(jobs)},
    }


@router.post("/globi/import/preview")
def preview_globi_import(
    version: str = Form(default="stable"),
    source_url: str = Form(default=""),
    include_insect_insect: bool = Form(default=True),
    keep_unknown_region: bool = Form(default=True),
    batch_size: int = Form(default=1000),
    interaction_types_json: str = Form(default="[]"),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = GlobiImportService(db)
    path: Path | None = None
    downloaded = False
    try:
        options = _globi_options(
            include_insect_insect,
            keep_unknown_region,
            batch_size,
            interaction_types_json,
        )
        if file is not None:
            path = _stage_globi_upload(file)
        elif source_url.strip():
            path = service.download(source_url.strip())
            downloaded = True
        else:
            raise ValueError("请上传 GloBI CSV/TSV 文件或填写官方下载地址")
        data = {
            "version": version.strip() or "stable",
            "source_name": file.filename if file is not None else source_url.strip(),
            "checksum": service.checksum(path),
            "filters": options.as_dict(),
            "stats": service.preview(path, options),
        }
        return {"code": 0, "message": "globi import preview", "data": data}
    except Exception as exc:
        _raise_graph_error(exc)
    finally:
        if path is not None and (file is not None or downloaded):
            path.unlink(missing_ok=True)


@router.post("/globi/import")
def start_globi_import(
    version: str = Form(default="stable"),
    source_url: str = Form(default=""),
    include_insect_insect: bool = Form(default=True),
    keep_unknown_region: bool = Form(default=True),
    batch_size: int = Form(default=1000),
    interaction_types_json: str = Form(default="[]"),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    admin: UserModel = Depends(get_admin_user),
):
    staged_path: Path | None = None
    try:
        options = _globi_options(
            include_insect_insect,
            keep_unknown_region,
            batch_size,
            interaction_types_json,
        )
        if file is not None:
            staged_path = _stage_globi_upload(file)
        run = GlobiImportService(db).create_run(
            version=version,
            source_url="" if file is not None else source_url,
            source_name=file.filename if file is not None else source_url,
            staged_path=str(staged_path or ""),
            options=options,
            created_by=admin.id,
            delete_staged_after=staged_path is not None,
        )
        db.commit()
        return {"code": 0, "message": "globi import queued", "data": run}
    except Exception as exc:
        db.rollback()
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        _raise_graph_error(exc)


@router.get("/globi/import")
def list_globi_imports(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    return {
        "code": 0,
        "message": "success",
        "data": GlobiImportService(db).list_runs(limit),
    }


@router.get("/globi/import/{run_id}/summary")
def get_globi_import_summary(
    run_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        data = GlobiImportService(db).summary(run_id)
    except Exception as exc:
        _raise_graph_error(exc)
    return {"code": 0, "message": "success", "data": data}


@router.post("/globi/import/{run_id}/rollback")
def rollback_globi_import(
    run_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        data = GlobiImportService(db).rollback(run_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "globi import rolled back", "data": data}


@router.post("/globi/import/{run_id}/retry")
def retry_globi_import(
    run_id: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        data = GlobiImportService(db).retry(run_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {"code": 0, "message": "globi import queued for retry", "data": data}


@router.get("/ecology-graph/sync")
def get_ecology_graph_sync(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    return {
        "code": 0,
        "message": "success",
        "data": EcologyGraphSyncService(db).status_payload(limit=limit),
    }


@router.get("/graph/evidence-chunks")
def graph_evidence_chunks(
    source: str = "",
    query: str = "",
    relation_id: str = "",
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        chunks = KnowledgeGraphService(db).evidence_chunks(
            source=source,
            query=query,
            relation_id=relation_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_graph_error(exc)
    return {"code": 0, "message": "success", "data": chunks}


@router.post("/graph/rebuild-mentions")
def rebuild_graph_mentions(
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = KnowledgeGraphService(db)
    try:
        count = service.rebuild_all_mentions()
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {
        "code": 0,
        "message": "graph mentions rebuilt",
        "data": {"mention_count": count},
    }


@router.get("/graph/entities/{entity_id}/neighbors")
def graph_entity_neighbors(
    entity_id: str,
    hops: int = Query(1, ge=1, le=2),
    predicates: str = "",
    db: Session = Depends(get_db),
    _user: UserModel = Depends(get_current_user),
):
    predicate_list = [
        item.strip() for item in predicates.split(",") if item.strip()
    ]
    data = KnowledgeGraphService(db).expand_neighbors(
        entity_id,
        hops=hops,
        predicates=predicate_list or None,
    )
    return {"code": 0, "message": "success", "data": data}


@router.post("/graph/import")
def import_graph_json(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        data = KnowledgeGraphService(db).import_graph_json(payload)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_graph_error(exc)
    return {
        "code": 0,
        "message": "knowledge graph imported",
        "data": data,
    }

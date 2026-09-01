import asyncio
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_admin_user, get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import (
    CurriculumChunkModel,
    CurriculumSourceModel,
    RagRecordModel,
    UserModel,
)
from app.services.curriculum_knowledge_service import (
    CurriculumFileError,
    CurriculumKnowledgeService,
    checksum_chunks,
    normalize_source,
    now_iso,
)
from app.services.curriculum_vector_service import CurriculumVectorUnavailable


router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])
EXPORT_ENTRY = "curriculum.json"
EXPORT_VERSION = 1


def serialize_source(row: CurriculumSourceModel) -> dict:
    return {
        "source": row.source,
        "extension": Path(row.source).suffix.lower(),
        "chunk_count": int(row.chunk_count or 0),
        "vector_chunk_count": int(row.vector_chunk_count or 0),
        "vector_status": row.vector_status or "pending",
        "embedding_model": row.embedding_model or "",
        "last_error": row.last_error or "",
        "updated_at": row.updated_at or "",
    }


def get_source_summary(db: Session, source: str) -> dict:
    row = db.get(CurriculumSourceModel, source)
    if not row:
        raise HTTPException(status_code=404, detail="课标不存在")
    return serialize_source(row)


@router.get("/files")
def list_curriculum_files(
    db: Session = Depends(get_db),
    _user: UserModel = Depends(get_current_user),
):
    service = CurriculumKnowledgeService(db)
    service.ensure_source_records()
    db.commit()
    rows = (
        db.query(CurriculumSourceModel)
        .order_by(CurriculumSourceModel.updated_at.desc())
        .all()
    )
    return {
        "code": 0,
        "message": "success",
        "data": [serialize_source(row) for row in rows],
    }


@router.post("/files")
async def upload_curriculum_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    settings = get_settings()
    try:
        source = CurriculumKnowledgeService.safe_source_name(file.filename or "")
    except CurriculumFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = await file.read(settings.upload_max_file_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    if len(data) > settings.upload_max_file_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"单个文件不能超过 {settings.upload_max_file_bytes // (1024 * 1024)} MB",
        )

    try:
        content = await asyncio.to_thread(
            CurriculumKnowledgeService.extract_bytes,
            source,
            data,
        )
        CurriculumKnowledgeService(db, settings).ingest(source, content)
        db.commit()
    except CurriculumFileError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="课标导入失败，请稍后重试") from exc

    return {
        "code": 0,
        "message": "curriculum imported",
        "data": get_source_summary(db, source),
    }


@router.delete("/files")
def delete_curriculum_file(
    source: str,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    try:
        normalized_source = normalize_source(source)
    except CurriculumFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    deleted = CurriculumKnowledgeService(db).delete_source(normalized_source)
    if not deleted:
        db.rollback()
        raise HTTPException(status_code=404, detail="课标不存在")
    db.commit()
    return {"code": 0, "message": "curriculum deleted", "data": None}


@router.get("/status")
def curriculum_status(
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = CurriculumKnowledgeService(db)
    status = service.status()
    db.commit()
    return {"code": 0, "message": "success", "data": status}


@router.post("/vector/rebuild")
def rebuild_curriculum_vectors(
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = CurriculumKnowledgeService(db)
    try:
        count = service.rebuild_vector_index()
        db.commit()
    except CurriculumVectorUnavailable as exc:
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "code": 0,
        "message": "curriculum vectors rebuilt",
        "data": {"vector_chunk_count": count, "status": service.status()},
    }


@router.get("/retrievals")
def list_curriculum_retrievals(
    limit: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    query = db.query(RagRecordModel)
    if session_id:
        query = query.filter(RagRecordModel.session_id == session_id)
    rows = query.order_by(RagRecordModel.created_at.desc()).limit(limit * 3).all()
    records = []
    for row in rows:
        try:
            source = json.loads(row.source_json or "{}")
        except json.JSONDecodeError:
            continue
        mode = str(source.get("mode") or "")
        if not mode.startswith("local_"):
            continue
        records.append(
            {
                "id": row.id,
                "session_id": row.session_id,
                "stage_id": row.stage_id,
                "query": row.query or "",
                "mode": mode,
                "vector_error": source.get("vector_error") or "",
                "records": source.get("records") or [],
                "created_at": row.created_at,
            }
        )
        if len(records) >= limit:
            break
    return {"code": 0, "message": "success", "data": records}


@router.get("/export")
def export_curriculum_bundle(
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    service = CurriculumKnowledgeService(db)
    service.ensure_source_records()
    db.commit()
    sources = []
    for state in (
        db.query(CurriculumSourceModel)
        .order_by(CurriculumSourceModel.source.asc())
        .all()
    ):
        chunks = (
            db.query(CurriculumChunkModel)
            .filter(CurriculumChunkModel.source == state.source)
            .order_by(CurriculumChunkModel.source_index.asc())
            .all()
        )
        sources.append(
            {
                "source": state.source,
                "checksum": state.checksum,
                "chunks": [
                    {"source_index": row.source_index, "content": row.content}
                    for row in chunks
                ],
            }
        )
    payload = {
        "version": EXPORT_VERSION,
        "exported_at": now_iso(),
        "embedding_model": get_settings().curriculum_embedding_model,
        "sources": sources,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            EXPORT_ENTRY,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="curriculum-knowledge.zip"'
        },
    )


@router.post("/import")
async def import_curriculum_bundle(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(get_admin_user),
):
    settings = get_settings()
    data = await file.read(settings.upload_max_file_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="知识库导入包不能为空")
    if len(data) > settings.upload_max_file_bytes:
        limit_mb = settings.upload_max_file_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"知识库导入包不能超过 {limit_mb} MB")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if EXPORT_ENTRY not in archive.namelist():
                raise CurriculumFileError("导入包缺少 curriculum.json")
            if archive.getinfo(EXPORT_ENTRY).file_size > settings.upload_max_file_bytes * 5:
                raise CurriculumFileError("导入包解压后的数据过大")
            payload = json.loads(archive.read(EXPORT_ENTRY).decode("utf-8"))
        if payload.get("version") != EXPORT_VERSION:
            raise CurriculumFileError("不支持的知识库导入包版本")
        sources = payload.get("sources")
        if not isinstance(sources, list):
            raise CurriculumFileError("知识库导入包格式无效")
        service = CurriculumKnowledgeService(db, settings)
        imported_sources = 0
        imported_chunks = 0
        for item in sources:
            if not isinstance(item, dict):
                raise CurriculumFileError("知识库导入包包含无效课标条目")
            source = normalize_source(str(item.get("source") or ""))
            chunk_items = item.get("chunks") or []
            if not isinstance(chunk_items, list):
                raise CurriculumFileError(f"课标 {source} 的片段格式无效")
            if any(not isinstance(chunk, dict) for chunk in chunk_items):
                raise CurriculumFileError(f"课标 {source} 包含无效片段")
            ordered = sorted(
                chunk_items,
                key=lambda chunk: int(chunk.get("source_index", 0)),
            )
            chunks = [str(chunk.get("content") or "") for chunk in ordered]
            expected_checksum = str(item.get("checksum") or "")
            actual_checksum = checksum_chunks(chunks)
            if expected_checksum and expected_checksum != actual_checksum:
                raise CurriculumFileError(f"课标 {source} 的内容校验失败")
            count = service.ingest_chunks(
                source,
                chunks,
                checksum=expected_checksum or actual_checksum,
            )
            imported_sources += 1
            imported_chunks += count
        db.commit()
    except (CurriculumFileError, json.JSONDecodeError, zipfile.BadZipFile, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="知识库导入失败") from exc

    return {
        "code": 0,
        "message": "curriculum bundle imported",
        "data": {
            "source_count": imported_sources,
            "chunk_count": imported_chunks,
        },
    }

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_admin_user, get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import CurriculumChunkModel, UserModel
from app.services.curriculum_knowledge_service import (
    CurriculumFileError,
    CurriculumKnowledgeService,
)


router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])


def serialize_source(row) -> dict:
    source = str(row.source)
    return {
        "source": source,
        "extension": Path(source).suffix.lower(),
        "chunk_count": int(row.chunk_count or 0),
        "updated_at": row.updated_at or "",
    }


def source_query(db: Session):
    return db.query(
        CurriculumChunkModel.source.label("source"),
        func.count(CurriculumChunkModel.id).label("chunk_count"),
        func.max(CurriculumChunkModel.created_at).label("updated_at"),
    ).group_by(CurriculumChunkModel.source)


def get_source_summary(db: Session, source: str) -> dict:
    row = source_query(db).filter(CurriculumChunkModel.source == source).first()
    if not row:
        raise HTTPException(status_code=404, detail="课标不存在")
    return serialize_source(row)


@router.get("/files")
def list_curriculum_files(
    db: Session = Depends(get_db),
    _user: UserModel = Depends(get_current_user),
):
    rows = source_query(db).order_by(func.max(CurriculumChunkModel.created_at).desc()).all()
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
    normalized_source = source.strip()
    if not normalized_source:
        raise HTTPException(status_code=400, detail="课标来源不能为空")
    deleted = (
        db.query(CurriculumChunkModel)
        .filter(CurriculumChunkModel.source == normalized_source)
        .delete(synchronize_session=False)
    )
    if not deleted:
        db.rollback()
        raise HTTPException(status_code=404, detail="课标不存在")
    db.commit()
    return {"code": 0, "message": "curriculum deleted", "data": None}

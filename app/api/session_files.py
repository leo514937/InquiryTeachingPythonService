import asyncio
import datetime as dt
import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import SessionFileModel, UserModel
from app.services.session_access_service import get_owned_session
from app.services.session_file_service import FileExtractionError, SessionFileService


router = APIRouter(prefix="/api/sessions", tags=["session-files"])


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def serialize_file(item: SessionFileModel) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "extension": item.extension,
        "mime_type": item.mime_type or "",
        "size_bytes": item.size_bytes or 0,
        "extracted_chars": item.extracted_chars or 0,
        "status": item.status,
        "error_message": item.error_message or "",
        "created_at": item.created_at,
    }


@router.get("/{session_id}/files")
def list_session_files(
    session_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    get_owned_session(db, session_id, user.id)
    files = (
        db.query(SessionFileModel)
        .filter(SessionFileModel.session_id == session_id)
        .order_by(SessionFileModel.created_at.asc(), SessionFileModel.id.asc())
        .all()
    )
    return {
        "code": 0,
        "message": "success",
        "data": [serialize_file(item) for item in files],
    }


@router.post("/{session_id}/files")
async def upload_session_file(
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    get_owned_session(db, session_id, user.id)
    settings = get_settings()
    file_count = (
        db.query(func.count(SessionFileModel.id))
        .filter(SessionFileModel.session_id == session_id)
        .scalar()
        or 0
    )
    if file_count >= settings.upload_max_files_per_session:
        raise HTTPException(
            status_code=409,
            detail=f"每个会话最多上传 {settings.upload_max_files_per_session} 个文件",
        )

    try:
        display_name = SessionFileService.safe_display_name(file.filename or "")
        extension = SessionFileService.extension_for(display_name)
    except FileExtractionError as exc:
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

    file_id = f"file_{uuid.uuid4().hex[:12]}"
    relative_path = SessionFileService.relative_storage_path(session_id, file_id, extension)
    mime_type = file.content_type or mimetypes.guess_type(display_name)[0] or ""
    record = SessionFileModel(
        id=file_id,
        session_id=session_id,
        name=display_name,
        extension=extension,
        mime_type=mime_type,
        size_bytes=len(data),
        extracted_text="",
        extracted_chars=0,
        status="processing",
        error_message="",
        stored_path=relative_path.as_posix(),
        created_at=now_iso(),
    )
    db.add(record)
    db.commit()

    try:
        await asyncio.to_thread(SessionFileService.write_file, relative_path, data)
        extracted_text = await asyncio.to_thread(
            SessionFileService.extract_text,
            relative_path,
            extension,
        )
        ready_chars = (
            db.query(func.coalesce(func.sum(SessionFileModel.extracted_chars), 0))
            .filter(
                SessionFileModel.session_id == session_id,
                SessionFileModel.status == "ready",
            )
            .scalar()
            or 0
        )
        if ready_chars + len(extracted_text) > settings.upload_max_total_chars:
            raise FileExtractionError(
                f"会话参考资料正文总计不能超过 {settings.upload_max_total_chars} 字符"
            )
        record.extracted_text = extracted_text
        record.extracted_chars = len(extracted_text)
        record.status = "ready"
        record.error_message = ""
    except Exception as exc:
        record.extracted_text = ""
        record.extracted_chars = 0
        record.status = "failed"
        record.error_message = (
            str(exc)[:1000]
            if isinstance(exc, FileExtractionError)
            else "文件处理失败，请检查文件后重试"
        )

    db.commit()
    db.refresh(record)
    return {"code": 0, "message": "success", "data": serialize_file(record)}


@router.delete("/{session_id}/files/{file_id}")
def delete_session_file(
    session_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    get_owned_session(db, session_id, user.id)
    record = (
        db.query(SessionFileModel)
        .filter(
            SessionFileModel.id == file_id,
            SessionFileModel.session_id == session_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    SessionFileService.delete_stored_file(record.stored_path)
    db.delete(record)
    db.commit()
    return {"code": 0, "message": "file deleted", "data": None}

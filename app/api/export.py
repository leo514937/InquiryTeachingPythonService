from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import SessionModel, StageOutputModel
from app.services.export_service import MarkdownExportService


router = APIRouter(prefix="/api/sessions", tags=["export"])


@router.get("/{session_id}/export")
def export_session(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    outputs = (
        db.query(StageOutputModel)
        .filter(StageOutputModel.session_id == session_id)
        .order_by(StageOutputModel.order_index.asc())
        .all()
    )
    markdown = MarkdownExportService.compile_lesson_plan(sess.topic, sess.flow_name, outputs)
    filename = quote(f"{sess.topic}-探究式教案.md")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    return Response(content=markdown, media_type="text/markdown; charset=utf-8", headers=headers)

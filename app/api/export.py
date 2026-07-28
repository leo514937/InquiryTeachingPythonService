from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import StageOutputModel, UserModel
from app.services.export_service import MarkdownExportService
from app.services.session_access_service import get_owned_session


router = APIRouter(prefix="/api/sessions", tags=["export"])


@router.get("/{session_id}/export")
def export_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    sess = get_owned_session(db, session_id, user.id)

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

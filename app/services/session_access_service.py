from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import SessionModel


def get_owned_session(db: Session, session_id: str, user_id: str) -> SessionModel:
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.owner_user_id == user_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

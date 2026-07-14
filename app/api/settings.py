from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import ChatModeRequest
from app.services.app_settings_service import get_global_chat_mode, set_global_chat_mode


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/chat-mode")
def read_chat_mode(db: Session = Depends(get_db)):
    return {
        "code": 0,
        "message": "success",
        "data": {"chat_mode": get_global_chat_mode(db)},
    }


@router.put("/chat-mode")
def update_chat_mode(payload: ChatModeRequest, db: Session = Depends(get_db)):
    chat_mode = set_global_chat_mode(db, payload.chat_mode)
    return {
        "code": 0,
        "message": "chat mode updated",
        "data": {"chat_mode": chat_mode},
    }

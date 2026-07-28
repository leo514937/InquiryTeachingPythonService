from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import UserModel
from app.schemas import ChatModeRequest
from app.services.app_settings_service import get_user_chat_mode, set_user_chat_mode


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/chat-mode")
def read_chat_mode(
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    return {
        "code": 0,
        "message": "success",
        "data": {"chat_mode": get_user_chat_mode(user)},
    }


@router.put("/chat-mode")
def update_chat_mode(
    payload: ChatModeRequest,
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    chat_mode = set_user_chat_mode(db, user, payload.chat_mode)
    return {
        "code": 0,
        "message": "chat mode updated",
        "data": {"chat_mode": chat_mode},
    }

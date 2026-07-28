from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserModel
from app.services.auth_service import AUTH_COOKIE_NAME, resolve_token_user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> UserModel:
    user = resolve_token_user(db, request.cookies.get(AUTH_COOKIE_NAME))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return user

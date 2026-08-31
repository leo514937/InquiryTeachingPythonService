from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import UserModel
from app.schemas import LoginRequest, RegisterRequest
from app.services.auth_service import (
    AUTH_COOKIE_NAME,
    clear_auth_cookie,
    login_user,
    register_user,
    revoke_token,
    serialize_user,
    set_auth_cookie,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user, token = register_user(db, payload.username, payload.password)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在") from exc

    set_auth_cookie(response, token)
    return {"code": 0, "message": "registered", "data": serialize_user(user)}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    result = login_user(db, payload.username, payload.password, require_admin=False)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    user, token = result
    set_auth_cookie(response, token)
    return {"code": 0, "message": "logged in", "data": serialize_user(user)}


@router.post("/admin/register")
def register_admin(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    if not get_settings().admin_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员注册当前已关闭",
        )
    try:
        user, token = register_user(
            db,
            payload.username,
            payload.password,
            is_admin=True,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在") from exc

    set_auth_cookie(response, token)
    return {"code": 0, "message": "admin registered", "data": serialize_user(user)}


@router.post("/admin/login")
def login_admin(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    result = login_user(db, payload.username, payload.password, require_admin=True)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员用户名或密码错误",
        )

    user, token = result
    set_auth_cookie(response, token)
    return {"code": 0, "message": "admin logged in", "data": serialize_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_token(db, request.cookies.get(AUTH_COOKIE_NAME))
    clear_auth_cookie(response)
    return {"code": 0, "message": "logged out", "data": None}


@router.get("/me")
def me(user: UserModel = Depends(get_current_user)):
    return {"code": 0, "message": "success", "data": serialize_user(user)}

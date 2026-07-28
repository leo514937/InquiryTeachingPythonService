import base64
import datetime as dt
import hashlib
import hmac
import secrets
import uuid

from fastapi import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AppSettingModel, AuthSessionModel, SessionModel, UserModel


AUTH_COOKIE_NAME = "inquiry_auth"
MAIN_MODE = "main"
SUBAGENT_MODE = "subagent"
VALID_CHAT_MODES = {MAIN_MODE, SUBAGENT_MODE}


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def now_iso() -> str:
    return now_utc().astimezone().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"scrypt$16384$8$1${encode(salt)}${encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_encoded, digest_encoded = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_encoded.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_encoded.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def serialize_user(user: UserModel) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "chat_mode": user.chat_mode if user.chat_mode in VALID_CHAT_MODES else MAIN_MODE,
    }


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(db: Session, user: UserModel) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = now_utc() + dt.timedelta(days=get_settings().auth_session_days)
    db.add(
        AuthSessionModel(
            id=new_id("auth"),
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=expires_at.isoformat(),
            created_at=now_iso(),
        )
    )
    return token


def register_user(db: Session, username: str, password: str) -> tuple[UserModel, str]:
    normalized_username = normalize_username(username)
    existing = db.query(UserModel).filter(UserModel.username == normalized_username).first()
    if existing:
        raise ValueError("用户名已存在")

    is_first_user = db.query(UserModel).count() == 0
    initial_chat_mode = MAIN_MODE
    if is_first_user:
        legacy_setting = (
            db.query(AppSettingModel)
            .filter(AppSettingModel.key == "global_chat_mode")
            .first()
        )
        if legacy_setting and legacy_setting.value in VALID_CHAT_MODES:
            initial_chat_mode = legacy_setting.value

    user = UserModel(
        id=new_id("user"),
        username=normalized_username,
        password_hash=hash_password(password),
        chat_mode=initial_chat_mode,
        created_at=now_iso(),
    )
    db.add(user)
    db.flush()

    if is_first_user:
        (
            db.query(SessionModel)
            .filter(SessionModel.owner_user_id.is_(None))
            .update({SessionModel.owner_user_id: user.id}, synchronize_session=False)
        )

    token = issue_token(db, user)
    db.commit()
    db.refresh(user)
    return user, token


def login_user(db: Session, username: str, password: str) -> tuple[UserModel, str] | None:
    user = (
        db.query(UserModel)
        .filter(UserModel.username == normalize_username(username))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        return None

    token = issue_token(db, user)
    db.commit()
    db.refresh(user)
    return user, token


def resolve_token_user(db: Session, token: str | None) -> UserModel | None:
    if not token:
        return None

    auth_session = (
        db.query(AuthSessionModel)
        .filter(AuthSessionModel.token_hash == token_hash(token))
        .first()
    )
    if not auth_session:
        return None

    try:
        expires_at = dt.datetime.fromisoformat(auth_session.expires_at)
    except ValueError:
        expires_at = now_utc()
    if expires_at <= now_utc():
        db.delete(auth_session)
        db.commit()
        return None

    return db.query(UserModel).filter(UserModel.id == auth_session.user_id).first()


def revoke_token(db: Session, token: str | None) -> None:
    if token:
        db.query(AuthSessionModel).filter(
            AuthSessionModel.token_hash == token_hash(token)
        ).delete(synchronize_session=False)
        db.commit()


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")

import datetime as dt

from sqlalchemy.orm import Session

from app.db.models import AppSettingModel


CHAT_MODE_KEY = "global_chat_mode"
MAIN_MODE = "main"
SUBAGENT_MODE = "subagent"
VALID_CHAT_MODES = {MAIN_MODE, SUBAGENT_MODE}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def get_global_chat_mode(db: Session) -> str:
    row = db.query(AppSettingModel).filter(AppSettingModel.key == CHAT_MODE_KEY).first()
    if row and row.value in VALID_CHAT_MODES:
        return row.value

    timestamp = now_iso()
    if row:
        row.value = MAIN_MODE
        row.updated_at = timestamp
    else:
        db.add(
            AppSettingModel(
                key=CHAT_MODE_KEY,
                value=MAIN_MODE,
                updated_at=timestamp,
            )
        )
    db.commit()
    return MAIN_MODE


def set_global_chat_mode(db: Session, mode: str) -> str:
    if mode not in VALID_CHAT_MODES:
        raise ValueError(f"Unsupported chat mode: {mode}")

    row = db.query(AppSettingModel).filter(AppSettingModel.key == CHAT_MODE_KEY).first()
    timestamp = now_iso()
    if row:
        row.value = mode
        row.updated_at = timestamp
    else:
        db.add(
            AppSettingModel(
                key=CHAT_MODE_KEY,
                value=mode,
                updated_at=timestamp,
            )
        )
    db.commit()
    return mode

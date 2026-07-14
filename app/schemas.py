from typing import Literal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    topic: str = Field(min_length=1)
    flow_name: str = "inquiry_7_stage"


class SelectFlowRequest(BaseModel):
    flow_name: str
    clear_messages: bool = True


class ChatRequest(BaseModel):
    type: Literal["chat", "sys_action"] = "chat"
    message: str = ""
    action: Literal["next_stage", "prev_stage", "intro", "confirm_stage"] | None = None
    final_content: str | None = None


class RollbackRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=20)
    stage_back: bool = False


class DraftUpdateRequest(BaseModel):
    draft_content: str


class ConfirmStageRequest(BaseModel):
    final_content: str


class ApiMessage(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict | list | None = None

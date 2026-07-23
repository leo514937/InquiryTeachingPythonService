from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, export, flows, health, sessions, settings
from app.db.database import Base, engine
from app.db.migrations import ensure_schema_compatibility


Base.metadata.create_all(bind=engine)
ensure_schema_compatibility()

app = FastAPI(
    title="AI 教师探究式教学指导 Python Service",
    version="0.1.0",
    description="无登录校验的探究式教学设计后端服务，参考 GoMAown 的流程选择、会话状态和专家路由链路。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(flows.router)
app.include_router(sessions.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(export.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)

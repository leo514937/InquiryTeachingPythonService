from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, export, flows, health, sessions, settings
from app.core.config import get_settings
from app.db.database import Base, engine
from app.db.migrations import ensure_schema_compatibility


Base.metadata.create_all(bind=engine)
ensure_schema_compatibility()

app = FastAPI(
    title="AI 教师探究式教学指导 Python Service",
    version="0.1.0",
    description="支持多用户会话隔离的探究式教学设计后端服务。",
)

app_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(app_settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(flows.router)
app.include_router(sessions.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(export.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)

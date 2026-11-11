import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, chat, curriculum, export, flows, health, knowledge, knowledge_sources, session_files, sessions, study_projects
from app.core.config import get_settings
from app.db.database import Base, engine, SessionLocal
from app.db.migrations import ensure_schema_compatibility
from app.services.ecology_graph_sync_service import EcologyGraphWorker
from app.services.globi_import_service import GlobiImportWorker


Base.metadata.create_all(bind=engine)
ensure_schema_compatibility()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    worker = EcologyGraphWorker()
    task = asyncio.create_task(worker.run(), name="ecology-graph-worker")
    globi_worker = GlobiImportWorker()
    globi_task = asyncio.create_task(globi_worker.run(), name="globi-import-worker")
    workspace_worker = None
    workspace_task = None
    if get_settings().inquiry_workspace_enabled:
        from app.workspace.integrations.llm import StrictLLM
        from app.workspace.runtime.worker import WorkspaceWorker
        workspace_worker = WorkspaceWorker(SessionLocal, StrictLLM(get_settings()))
        workspace_task = asyncio.create_task(workspace_worker.run(), name="inquiry-workspace-worker")
    try:
        yield
    finally:
        worker.stop()
        globi_worker.stop()
        task.cancel()
        globi_task.cancel()
        if workspace_worker:
            workspace_worker.stop()
        if workspace_task:
            workspace_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(asyncio.CancelledError):
            await globi_task
        if workspace_task:
            with suppress(asyncio.CancelledError):
                await workspace_task

app = FastAPI(
    title="AI 教师探究式教学指导 Python Service",
    version="0.1.0",
    description="支持多用户会话隔离的探究式教学设计后端服务。",
    lifespan=lifespan,
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
app.include_router(agents.router)
app.include_router(sessions.router)
app.include_router(study_projects.router)
app.include_router(session_files.router)
app.include_router(curriculum.router)
app.include_router(knowledge.router)
app.include_router(knowledge_sources.router)
app.include_router(chat.router)
app.include_router(export.router)

if app_settings.inquiry_workspace_enabled:
    from app.workspace.api import router as inquiry_workspace_router
    from app.workspace.migrations import ensure_workspace_schema

    ensure_workspace_schema(engine)
    app.include_router(inquiry_workspace_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)

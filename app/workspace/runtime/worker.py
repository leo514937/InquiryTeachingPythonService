import asyncio
import logging

from sqlalchemy import or_

from app.workspace.artifacts.service import _now
from app.workspace.models import WorkspaceRun
from app.workspace.runtime.runs import execute_builtin_run

logger = logging.getLogger(__name__)


class WorkspaceWorker:
    def __init__(self, session_factory, model, poll_seconds=2, authorize=None):
        self.session_factory = session_factory
        self.model = model
        self.poll_seconds = poll_seconds
        self.authorize = authorize
        self.stopped = False

    def process_next(self):
        with self.session_factory() as db:
            row = (db.query(WorkspaceRun.id).filter(
                WorkspaceRun.cancel_requested == 0,
                or_(WorkspaceRun.status == 'queued',
                    (WorkspaceRun.status.in_(['planning', 'running']) & (WorkspaceRun.lease_until < _now()))),
            ).order_by(WorkspaceRun.created_at).first())
        if not row:
            return False
        execute_builtin_run(self.session_factory, row.id, self.model, authorize=self.authorize)
        return True

    async def run(self):
        while not self.stopped:
            try:
                worked = await asyncio.to_thread(self.process_next)
                if not worked:
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Workspace worker iteration failed')
                await asyncio.sleep(self.poll_seconds)

    def stop(self):
        self.stopped = True

"""Authenticated, resumable workspace event stream."""
import asyncio
import json

from fastapi import HTTPException

from app.core.sse import format_sse
from app.services.auth_service import resolve_token_user
from app.workspace.models import WorkspaceEvent


_ALLOWED_EVENT_KINDS = {
    'queued', 'planning', 'running', 'node_started', 'node_attempt', 'node_retry', 'node_succeeded',
    'node_failed', 'node_skipped', 'node_cancelled', 'node_result_discarded',
    'completed', 'failed', 'cancelled', 'cancel_requested', 'waiting_review', 'review_approved',
}
_SAFE_FIELDS = {'node_id', 'status', 'capability', 'attempts', 'error_code', 'nodes'}


def _safe_event(event):
    try:
        data = json.loads(event.data_json)
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    safe = {key: value for key, value in data.items()
            if key in _SAFE_FIELDS and isinstance(value, (str, int, bool, type(None)))}
    kind = event.kind if event.kind in _ALLOWED_EVENT_KINDS else 'update'
    return f'id: {event.sequence}\n' + format_sse(kind, safe)


async def follow_events(request, session_factory, token, workspace_id, run_id, cursor):
    from app.workspace.api import _owned_run
    heartbeat = 0
    while not await request.is_disconnected():
        try:
            with session_factory() as db:
                user = resolve_token_user(db, token)
                if user is None:
                    raise HTTPException(status_code=401, detail='请先登录')
                run = _owned_run(db, user, workspace_id, run_id)
                events = (db.query(WorkspaceEvent).filter(WorkspaceEvent.run_id == run_id,
                          WorkspaceEvent.sequence > cursor).order_by(WorkspaceEvent.sequence).limit(200).all())
                payloads = [(event.sequence, _safe_event(event)) for event in events]
                terminal = run.status in ('completed', 'failed', 'cancelled')
        except HTTPException:
            yield format_sse('access_revoked', {'message': '访问权限已失效'})
            return
        for sequence, payload in payloads:
            cursor = sequence
            yield payload
        if len(payloads) == 200:
            continue
        if terminal:
            return
        if heartbeat <= 0:
            yield ': heartbeat\n\n'
            heartbeat = 15
        await asyncio.sleep(1)
        heartbeat -= 1


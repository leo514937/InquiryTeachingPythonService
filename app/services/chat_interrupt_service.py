import asyncio
import threading
from dataclasses import dataclass


class ChatInterrupted(RuntimeError):
    """Raised when an active chat stream is cancelled by the client."""


@dataclass
class ActiveChat:
    request_id: str
    session_id: str
    user_id: str
    cancelled: threading.Event
    loop: asyncio.AbstractEventLoop | None = None
    task: asyncio.Task | None = None


class ChatInterruptRegistry:
    """Tracks active streams so a second request can cancel the running one."""

    def __init__(self) -> None:
        self._active: dict[str, ActiveChat] = {}
        self._lock = threading.Lock()

    def register(self, request_id: str, session_id: str, user_id: str) -> ActiveChat:
        with self._lock:
            if request_id in self._active:
                raise ValueError(f"Chat request already active: {request_id}")
            active = ActiveChat(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                cancelled=threading.Event(),
            )
            self._active[request_id] = active
            return active

    def bind_current_task(self, request_id: str) -> None:
        with self._lock:
            active = self._active.get(request_id)
            if not active:
                return
            active.loop = asyncio.get_running_loop()
            active.task = asyncio.current_task()

    def cancel(self, request_id: str, session_id: str, user_id: str) -> bool:
        with self._lock:
            active = self._active.get(request_id)
            if not active or active.session_id != session_id or active.user_id != user_id:
                return False
            active.cancelled.set()
            loop = active.loop
            task = active.task

        if loop and task:
            loop.call_soon_threadsafe(task.cancel)
        return True

    def is_cancelled(self, request_id: str) -> bool:
        with self._lock:
            active = self._active.get(request_id)
            return bool(active and active.cancelled.is_set())

    def unregister(self, request_id: str) -> None:
        with self._lock:
            self._active.pop(request_id, None)


chat_interruptions = ChatInterruptRegistry()

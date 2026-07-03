"""Process-global handles for async-task capture middleware and dispatcher (set from gateway lifespan)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from deerflow.persistence.async_task.repository import AsyncTaskRepository
from deerflow.runtime import RunContext, RunManager, StreamBridge


@dataclass
class AsyncTaskHandles:
    repo: AsyncTaskRepository | None
    bridge: StreamBridge | None
    run_manager: RunManager | None
    run_context_factory: Callable[[], RunContext] | None


_handles: AsyncTaskHandles | None = None


def set_async_task_handles(h: AsyncTaskHandles | None) -> None:
    global _handles
    _handles = h


def get_async_task_handles() -> AsyncTaskHandles | None:
    return _handles

"""Thread-level SSE for async_tasks updates + webhook callback for webhook-only rows."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.gateway.async_task_dispatcher import publish_async_task_manual
from app.gateway.deps import get_run_manager
from app.gateway.routers.threads import _require_user
from app.gateway.services import format_sse
from deerflow.runtime import END_SENTINEL, HEARTBEAT_SENTINEL
from deerflow.runtime.async_tasks.thread_bridge import sse_channel_for_thread

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads", tags=["async_tasks"])

try:
    from extensions.auth.dependencies import CurrentUser, get_current_user_optional
except Exception:  # pragma: no cover
    CurrentUser = Any  # type: ignore[misc,assignment]

    async def get_current_user_optional():  # type: ignore[no-redef]
        return None


_TerminalStatus = Literal["succeeded", "failed", "cancelled", "timeout"]

_MAX_LAST_POLL_JSON = 4096


def _public_payload_preview(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    lp = payload.get("last_poll")
    if lp is None:
        return {}
    try:
        s = json.dumps(lp, default=str)
    except TypeError:
        s = str(lp)
    if len(s) > _MAX_LAST_POLL_JSON:
        return {"last_poll": {"preview": s[:_MAX_LAST_POLL_JSON] + "…"}}
    try:
        return {"last_poll": json.loads(s)}
    except json.JSONDecodeError:
        return {"last_poll": {"preview": s[:_MAX_LAST_POLL_JSON]}}


def _coerce_json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


def _async_task_row_to_response(row: Any) -> AsyncTaskResponse:
    from deerflow.persistence.async_task.model import AsyncTaskRow

    assert isinstance(row, AsyncTaskRow)
    return AsyncTaskResponse(
        id=row.id,
        task_kind=row.task_kind,
        status=row.status,
        display_name=row.display_name,
        external_ref=row.external_ref,
        source_run_id=row.source_run_id,
        source_tool_call_id=row.source_tool_call_id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
        next_poll_at=row.next_poll_at.isoformat() if row.next_poll_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        terminal_followup_done=bool(row.terminal_followup_done),
        error=_coerce_json_object(row.error),
        result=_coerce_json_object(row.result) if row.status in ("succeeded", "failed", "cancelled", "timeout") else None,
        poll_command=row.poll_command,
        payload=_public_payload_preview(dict(row.payload or {})),
    )


class AsyncTaskResponse(BaseModel):
    id: UUID
    task_kind: str
    status: str
    display_name: str | None = None
    external_ref: str | None = None
    source_run_id: str | None = None
    source_tool_call_id: str | None = None
    created_at: str
    updated_at: str
    next_poll_at: str | None = None
    finished_at: str | None = None
    terminal_followup_done: bool
    poll_command: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


async def _ensure_thread_async_tasks_access(
    *,
    request: Request,
    thread_id: str,
    user: CurrentUser,
) -> None:
    """Allow listing/streaming when the user has async_task rows or visible runs on this thread."""
    uid = str(getattr(user, "id", "") or "")
    repo = getattr(request.app.state, "async_task_repo", None)
    if repo is not None:
        rows = await repo.list_by_thread_for_user(thread_id, uid, limit=1)
        if rows:
            return
    run_mgr = get_run_manager(request)
    records = await run_mgr.list_by_thread(thread_id, user_id=uid)
    if records:
        return
    raise HTTPException(status_code=404, detail="Thread not found")


class AsyncTaskWebhookBody(BaseModel):
    status: _TerminalStatus
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    callback_secret: str | None = Field(default=None, description="Must match row.callback_secret when set")


@router.get("/{thread_id}/async_tasks", response_model=list[AsyncTaskResponse])
async def list_async_tasks(
    thread_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> list[AsyncTaskResponse]:
    user = _require_user(current_user, request)
    repo = getattr(request.app.state, "async_task_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="async_tasks persistence not configured")
    await _ensure_thread_async_tasks_access(request=request, thread_id=thread_id, user=user)
    rows = await repo.list_by_thread_for_user(thread_id, str(user.id), limit=limit)
    return [_async_task_row_to_response(r) for r in rows]


@router.get("/{thread_id}/async_tasks/stream")
async def stream_async_task_events(
    thread_id: str,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """Subscribe to ``custom`` SSE events for all async_tasks on this thread (not tied to one run)."""
    user = _require_user(current_user, request)
    await _ensure_thread_async_tasks_access(request=request, thread_id=thread_id, user=user)

    from app.gateway.deps import get_stream_bridge

    bridge = get_stream_bridge(request)
    channel = sse_channel_for_thread(thread_id)
    last_event_id = request.headers.get("Last-Event-ID")

    async def gen():
        try:
            async for entry in bridge.subscribe(channel, last_event_id=last_event_id):
                if await request.is_disconnected():
                    break
                if entry is HEARTBEAT_SENTINEL:
                    yield ": heartbeat\n\n"
                    continue
                if entry is END_SENTINEL:
                    break
                yield format_sse(entry.event, entry.data, event_id=entry.id or None)
        except Exception:
            logger.exception("async_tasks SSE stream failed thread=%s", thread_id)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{thread_id}/async_tasks/{task_id}/callback")
async def async_task_webhook_callback(
    thread_id: str,
    task_id: UUID,
    body: AsyncTaskWebhookBody,
    request: Request,
) -> dict[str, Any]:
    repo = getattr(request.app.state, "async_task_repo", None)
    bridge = getattr(request.app.state, "stream_bridge", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="async_tasks persistence not configured")

    row = await repo.load(task_id)
    if row is None or row.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Task not found")

    prev = row.status
    updated = await repo.apply_webhook_update(
        task_id,
        callback_secret=body.callback_secret,
        new_status=body.status,
        result=body.result,
        error=body.error,
    )
    if updated is None:
        raise HTTPException(status_code=403, detail="Invalid secret, status, or task state")

    if bridge:
        await publish_async_task_manual(bridge, thread_id=thread_id, row=updated, previous_status=prev)

    return {"ok": True, "task_id": str(task_id), "status": updated.status}

"""Capture submit envelopes from tool stdout and insert into async_tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.persistence.async_task import AsyncTaskRow
from deerflow.runtime.async_tasks.envelope import (
    redact_poll_command_from_submitted_envelope_text,
    resolve_submit_envelope,
    tool_message_content_to_text,
)
from deerflow.runtime.async_tasks.registry import AsyncTaskHandles, get_async_task_handles

logger = logging.getLogger(__name__)


async def _publish_async_task_started_tip(handles: AsyncTaskHandles, run_id: str, row: AsyncTaskRow) -> None:
    """Notify the active run SSE stream (same channel as graph ``custom`` events)."""
    bridge = handles.bridge
    if bridge is None:
        return
    payload = {
        "type": "async_task_started",
        "task_id": str(row.id),
        "task_kind": row.task_kind,
    }
    try:
        await bridge.publish(run_id, "custom", payload)
    except Exception:
        logger.debug("async_task_started custom event publish failed", exc_info=True)


def _runtime_context(request: ToolCallRequest) -> dict[str, Any]:
    out: dict[str, Any] = {}
    runtime = getattr(request, "runtime", None)
    if runtime is None:
        return out
    ctx = getattr(runtime, "context", None)
    if isinstance(ctx, dict):
        out.update(ctx)
    cfg = getattr(runtime, "config", None)
    if isinstance(cfg, dict):
        conf = cfg.get("configurable") or {}
        if isinstance(conf, dict):
            out.setdefault("thread_id", conf.get("thread_id"))
            out.setdefault("run_id", conf.get("run_id"))
            out.setdefault("user_id", conf.get("user_id"))
    return out


class AsyncTaskCaptureMiddleware(AgentMiddleware[AgentState]):
    """After a tool returns, parse stdout envelope (status=submitted) and persist async_tasks."""

    async def _capture(self, request: ToolCallRequest, result: ToolMessage | Command) -> None:
        tool_name = str(request.tool_call.get("name") or "")
        handles = get_async_task_handles()
        if handles is None or handles.repo is None:
            logger.info("async_task capture skipped: async_task handles or repo unset (tool=%s)", tool_name)
            return
        if not isinstance(result, ToolMessage):
            return
        if getattr(result, "status", None) == "error":
            logger.info(
                "async_task capture skipped: tool returned error status (tool=%s id=%s)",
                tool_name,
                request.tool_call.get("id"),
            )
            return
        ctx = _runtime_context(request)
        user_id = ctx.get("user_id")
        thread_id = ctx.get("thread_id")
        run_id = ctx.get("run_id")
        tool_call_id = str(request.tool_call.get("id") or "").strip()
        if not user_id or not thread_id or not run_id or not tool_call_id:
            logger.info(
                "async_task capture skipped: missing runtime context (tool=%s user_id=%s thread_id=%s run_id=%s tool_call_id=%s)",
                tool_name,
                bool(user_id),
                bool(thread_id),
                bool(run_id),
                bool(tool_call_id),
            )
            return
        text = tool_message_content_to_text(result.content)
        envelope = resolve_submit_envelope(text)
        if envelope is None:
            if tool_name == "bash" and "vasp" in text.lower():
                logger.info(
                    "async_task capture: bash output looks VASP-related but no valid submitted envelope (thread=%s run=%s chars=%s)",
                    thread_id,
                    run_id,
                    len(text),
                )
            return
        try:
            row = await handles.repo.insert_from_capture(
                user_id=str(user_id),
                thread_id=str(thread_id),
                source_run_id=str(run_id),
                source_tool_call_id=tool_call_id,
                envelope=envelope,
            )
        except Exception:
            logger.exception("async_task capture insert failed")
            return
        if row is None:
            logger.info(
                "async_task capture: insert skipped (duplicate source_tool_call_id?) thread=%s run=%s tool_call_id=%s",
                thread_id,
                run_id,
                tool_call_id,
            )
            return
        logger.info(
            "async_task captured: id=%s kind=%s thread=%s run=%s tool_call_id=%s",
            row.id,
            row.task_kind,
            thread_id,
            run_id,
            tool_call_id,
        )
        await _publish_async_task_started_tip(handles, str(run_id), row)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        try:
            result = handler(request)
        except GraphBubbleUp:
            raise
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return result
        loop.create_task(self._capture_safe(request, result))
        return result

    async def _capture_safe(self, request: ToolCallRequest, result: ToolMessage | Command) -> None:
        try:
            await self._capture(request, result)
        except Exception:
            logger.exception("async_task capture task failed")

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        try:
            result = await handler(request)
        except GraphBubbleUp:
            raise
        await self._capture(request, result)
        _redact_poll_command_from_tool_message(result)
        return result


def _redact_poll_command_from_tool_message(result: ToolMessage | Command) -> None:
    if not isinstance(result, ToolMessage):
        return
    content = result.content
    if isinstance(content, str):
        new_txt = redact_poll_command_from_submitted_envelope_text(content)
        if new_txt != content:
            result.content = new_txt
        return
    if isinstance(content, list):
        full = tool_message_content_to_text(content)
        new_full = redact_poll_command_from_submitted_envelope_text(full)
        if new_full == full:
            return
        if len(content) == 1 and isinstance(content[0], dict) and content[0].get("type") == "text":
            content[0]["text"] = new_full
            return
        result.content = new_full

"""Tests for async task capture middleware + run SSE tip."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from deerflow.agents.middlewares.async_task_capture_middleware import AsyncTaskCaptureMiddleware
from deerflow.runtime.async_tasks.registry import AsyncTaskHandles, set_async_task_handles


@pytest.fixture(autouse=True)
def _reset_async_task_handles():
    yield
    set_async_task_handles(None)


@pytest.mark.asyncio
async def test_capture_publishes_custom_after_insert():
    published: list[tuple[str, str, dict]] = []

    class _Bridge:
        async def publish(self, run_id: str, event: str, data: dict) -> None:
            published.append((run_id, event, data))

    row = MagicMock()
    row.id = uuid.uuid4()
    row.task_kind = "vasp_relax"

    repo = MagicMock()
    repo.insert_from_capture = AsyncMock(return_value=row)

    set_async_task_handles(
        AsyncTaskHandles(
            repo=repo,
            bridge=_Bridge(),
            run_manager=None,
            run_context_factory=None,
        )
    )

    env_line = '{"status":"submitted","task_kind":"vasp_relax","external_ref":"job-1"}'
    runtime = MagicMock()
    runtime.context = {"user_id": "u1", "thread_id": "th1", "run_id": "run-xyz"}
    runtime.config = None
    request = ToolCallRequest(
        tool_call={"name": "bash", "id": "tc-99", "args": {}},
        tool=None,
        state={},
        runtime=runtime,
    )
    tm = ToolMessage(content=f"ok\n{env_line}\n", tool_call_id="tc-99")

    mw = AsyncTaskCaptureMiddleware()
    await mw._capture(request, tm)

    repo.insert_from_capture.assert_awaited_once()
    assert len(published) == 1
    rid, ev, payload = published[0]
    assert rid == "run-xyz"
    assert ev == "custom"
    assert payload["type"] == "async_task_started"
    assert payload["task_kind"] == "vasp_relax"
    assert payload["task_id"] == str(row.id)


@pytest.mark.asyncio
async def test_capture_no_publish_when_insert_returns_none():
    class _Bridge:
        async def publish(self, *_args, **_kwargs) -> None:
            raise AssertionError("should not publish")

    repo = MagicMock()
    repo.insert_from_capture = AsyncMock(return_value=None)

    set_async_task_handles(AsyncTaskHandles(repo=repo, bridge=_Bridge(), run_manager=None, run_context_factory=None))

    env_line = '{"status":"submitted","task_kind":"vasp_relax","external_ref":"job-1"}'
    runtime = MagicMock()
    runtime.context = {"user_id": "u1", "thread_id": "th1", "run_id": "run-xyz"}
    runtime.config = None
    request = ToolCallRequest(
        tool_call={"name": "bash", "id": "tc-99", "args": {}},
        tool=None,
        state={},
        runtime=runtime,
    )
    tm = ToolMessage(content=f"ok\n{env_line}\n", tool_call_id="tc-99")

    mw = AsyncTaskCaptureMiddleware()
    await mw._capture(request, tm)


@pytest.mark.asyncio
async def test_capture_no_publish_when_bridge_none():
    row = MagicMock()
    row.id = uuid.uuid4()
    row.task_kind = "x"

    repo = MagicMock()
    repo.insert_from_capture = AsyncMock(return_value=row)

    set_async_task_handles(AsyncTaskHandles(repo=repo, bridge=None, run_manager=None, run_context_factory=None))

    env_line = '{"status":"submitted","task_kind":"vasp_relax","external_ref":"job-1"}'
    runtime = MagicMock()
    runtime.context = {"user_id": "u1", "thread_id": "th1", "run_id": "run-xyz"}
    runtime.config = None
    request = ToolCallRequest(
        tool_call={"name": "bash", "id": "tc-99", "args": {}},
        tool=None,
        state={},
        runtime=runtime,
    )
    tm = ToolMessage(content=f"ok\n{env_line}\n", tool_call_id="tc-99")

    mw = AsyncTaskCaptureMiddleware()
    await mw._capture(request, tm)

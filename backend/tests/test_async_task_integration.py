"""Integration tests: async_tasks poll, SSE, terminal follow-up (requires PostgreSQL).

Set ``DATABASE_URL`` (see ``backend/tests/README.md``). Without it, tests skip.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.gateway.async_task_dispatcher import _run_one_poll, _start_terminal_followup
from deerflow.persistence.async_task.model import AsyncTaskRow
from deerflow.persistence.async_task.repository import AsyncTaskRepository
from deerflow.runtime import HEARTBEAT_SENTINEL
from deerflow.runtime.async_tasks.registry import AsyncTaskHandles, set_async_task_handles
from deerflow.runtime.async_tasks.thread_bridge import sse_channel_for_thread
from deerflow.runtime.runs.manager import RunManager
from deerflow.runtime.runs.store.memory import MemoryRunStore
from deerflow.runtime.runs.worker import RunContext
from deerflow.runtime.stream_bridge.memory import MemoryStreamBridge

pytestmark = pytest.mark.integration


def _normalize_async_url(url: str) -> str:
    if "+asyncpg" in url or "+psycopg" in url:
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def _async_tasks_ddl_statements() -> list[str]:
    path = Path(__file__).resolve().parent.parent / "scripts" / "sql" / "async_tasks_pg.sql"
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [b.strip() for b in body.split(";") if b.strip()]


@pytest.fixture
def _reset_handles():
    yield
    set_async_task_handles(None)


@pytest_asyncio.fixture
async def integration_engine_sf(_reset_handles):
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip("DATABASE_URL not set — see backend/tests/README.md")
    url = _normalize_async_url(url)
    try:
        engine = create_async_engine(url, pool_pre_ping=True)
    except ModuleNotFoundError as exc:
        pytest.skip(f"PostgreSQL async driver not installed: {exc}")

    async with engine.begin() as conn:
        for stmt in _async_tasks_ddl_statements():
            await conn.execute(text(stmt))

    sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield engine, sf
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_poll_publishes_async_task_update_on_thread_channel(integration_engine_sf):
    _engine, sf = integration_engine_sf
    repo = AsyncTaskRepository(sf)
    bridge = MemoryStreamBridge()

    app = MagicMock(spec=FastAPI)
    app.state = SimpleNamespace(async_task_repo=repo)

    set_async_task_handles(
        AsyncTaskHandles(
            repo=repo,
            bridge=bridge,
            run_manager=MagicMock(),
            run_context_factory=lambda: MagicMock(),
        )
    )

    thread_id = f"it-{uuid.uuid4().hex[:12]}"
    poll_out = '{"status":"completed","result":{"ok":true}}\n'

    envelope = {
        "status": "submitted",
        "task_kind": "integration_poll",
        "external_ref": f"ref-{uuid.uuid4().hex[:8]}",
        "poll_command": """echo '{"status":"completed","result":{"ok":true}}'""",
        "poll_interval_seconds": 60,
        "first_poll_delay_seconds": 0,
    }
    row = await repo.insert_from_capture(
        user_id="it-user",
        thread_id=thread_id,
        source_run_id=f"run-{uuid.uuid4().hex[:8]}",
        source_tool_call_id=f"tc-{uuid.uuid4().hex[:8]}",
        envelope=envelope,
    )
    assert row is not None

    async with sf() as session:
        await session.execute(sa_update(AsyncTaskRow).where(AsyncTaskRow.id == row.id).values(next_poll_at=datetime.now(UTC) - timedelta(minutes=5)))
        await session.commit()

    due = await repo.iter_due_poll_tasks(limit=10)
    assert any(r.id == row.id for r in due)
    row_due = next(r for r in due if r.id == row.id)

    ch = sse_channel_for_thread(thread_id)

    async def first_custom() -> dict:
        async for entry in bridge.subscribe(ch):
            if entry is HEARTBEAT_SENTINEL:
                continue
            if entry.event == "custom" and isinstance(entry.data, dict):
                if entry.data.get("type") == "async_task_update":
                    return entry.data
        raise AssertionError("no async_task_update on thread channel")

    waiter = asyncio.create_task(first_custom())

    class _Prov:
        def acquire(self, tid: str) -> str:
            return "sb"

        def get(self, sb_id: str):
            return self

        def execute_command(self, cmd: str) -> str:
            return poll_out

    with patch("app.gateway.async_task_dispatcher.get_sandbox_provider", return_value=_Prov()):
        await _run_one_poll(app, row_due)

    try:
        payload = await asyncio.wait_for(waiter, timeout=10.0)
    finally:
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter
    assert payload.get("type") == "async_task_update"
    assert payload.get("status") == "succeeded"
    assert payload.get("task_id") == str(row.id)

    reloaded = await repo.load(row.id)
    assert reloaded is not None
    assert reloaded.status == "succeeded"
    assert reloaded.payload.get("last_poll") is not None


@pytest.mark.asyncio
async def test_terminal_followup_creates_run_with_system_message(integration_engine_sf):
    _engine, sf = integration_engine_sf
    repo = AsyncTaskRepository(sf)
    bridge = MemoryStreamBridge()
    run_manager = RunManager(store=MemoryRunStore())

    def _ctx_factory() -> RunContext:
        return RunContext(
            checkpointer=MagicMock(),
            store=None,
            event_store=None,
            run_events_config=None,
            thread_store=None,
            app_config=None,
        )

    app = MagicMock(spec=FastAPI)
    app.state = SimpleNamespace(async_task_repo=repo)

    set_async_task_handles(
        AsyncTaskHandles(
            repo=repo,
            bridge=bridge,
            run_manager=run_manager,
            run_context_factory=_ctx_factory,
        )
    )

    thread_id = f"it-fu-{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC)
    row = AsyncTaskRow(
        id=uuid.uuid4(),
        user_id="it-user",
        thread_id=thread_id,
        source_run_id="src-run-1",
        source_tool_call_id=f"tc-{uuid.uuid4().hex[:8]}",
        task_kind="integration_followup",
        display_name="Integration task",
        status="succeeded",
        payload={},
        poll_command=None,
        poll_interval_seconds=1800,
        next_poll_at=None,
        external_ref="job-99",
        result={"ok": True},
        error=None,
        attempts=0,
        max_attempts=10,
        heartbeat_at=None,
        resume_run_id=None,
        terminal_followup_done=False,
        callback_secret=None,
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    async with sf() as session:
        session.add(row)
        await session.commit()

    mock_run = AsyncMock(return_value=None)
    with patch("deerflow.runtime.runs.worker.run_agent", mock_run):
        await _start_terminal_followup(app, row)

    runs = await run_manager.list_by_thread(thread_id)
    assert runs, "expected a follow-up run to be created"
    latest = runs[0]
    assert latest.metadata.get("trigger") == "async_task_terminal"
    assert latest.metadata.get("outcome") == "succeeded"

    graph_input = latest.kwargs.get("input") or {}
    msgs = graph_input.get("messages") or []
    assert msgs, "follow-up graph_input should contain messages"
    first = msgs[0]
    content = getattr(first, "content", None) or (first.get("content") if isinstance(first, dict) else "")
    assert "系统通知" in str(content) or "后台异步任务" in str(content)

    reloaded = await repo.load(row.id)
    assert reloaded is not None
    assert reloaded.terminal_followup_done is True
    assert reloaded.resume_run_id == latest.run_id

    if latest.task and not latest.task.done():
        latest.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await latest.task


@pytest.mark.asyncio
async def test_list_by_thread_for_user_filters_user(integration_engine_sf):
    _engine, sf = integration_engine_sf
    repo = AsyncTaskRepository(sf)
    thread_id = f"it-list-{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC)
    row_a = AsyncTaskRow(
        id=uuid.uuid4(),
        user_id="owner-a",
        thread_id=thread_id,
        source_run_id="run-a",
        source_tool_call_id=f"tc-{uuid.uuid4().hex[:8]}",
        task_kind="test_kind",
        display_name="A",
        status="queued",
        payload={},
        poll_command="echo '{}'",
        poll_interval_seconds=60,
        next_poll_at=now + timedelta(hours=1),
        external_ref=None,
        result=None,
        error=None,
        attempts=0,
        max_attempts=10,
        heartbeat_at=None,
        resume_run_id=None,
        terminal_followup_done=False,
        callback_secret=None,
        created_at=now,
        updated_at=now,
        finished_at=None,
    )
    row_b = AsyncTaskRow(
        id=uuid.uuid4(),
        user_id="owner-b",
        thread_id=thread_id,
        source_run_id="run-b",
        source_tool_call_id=f"tc-{uuid.uuid4().hex[:8]}",
        task_kind="test_kind",
        display_name="B",
        status="queued",
        payload={},
        poll_command="echo '{}'",
        poll_interval_seconds=60,
        next_poll_at=now + timedelta(hours=1),
        external_ref=None,
        result=None,
        error=None,
        attempts=0,
        max_attempts=10,
        heartbeat_at=None,
        resume_run_id=None,
        terminal_followup_done=False,
        callback_secret=None,
        created_at=now,
        updated_at=now,
        finished_at=None,
    )
    async with sf() as session:
        session.add(row_a)
        session.add(row_b)
        await session.commit()

    rows_owner_a = await repo.list_by_thread_for_user(thread_id, "owner-a", limit=50)
    assert len(rows_owner_a) == 1
    assert rows_owner_a[0].id == row_a.id

    rows_owner_b = await repo.list_by_thread_for_user(thread_id, "owner-b", limit=50)
    assert len(rows_owner_b) == 1
    assert rows_owner_b[0].id == row_b.id

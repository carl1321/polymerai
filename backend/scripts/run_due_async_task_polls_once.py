#!/usr/bin/env python3
"""One-shot: bump active async_tasks to due and run the same poll step as the gateway dispatcher.

Run from backend directory::

    uv run python scripts/run_due_async_task_polls_once.py

Uses the same DB and sandbox provider as a normal Gateway process (no HTTP server).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import update as sa_update

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_due_async_task_polls_once")


async def _main() -> int:
    load_dotenv(_REPO / ".env", override=False)

    from app.gateway.async_task_dispatcher import _run_one_poll
    from deerflow.config.app_config import get_app_config
    from deerflow.persistence.async_task.model import AsyncTaskRow
    from deerflow.persistence.async_task.repository import AsyncTaskRepository
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
    from deerflow.runtime.async_tasks.registry import AsyncTaskHandles, set_async_task_handles
    from deerflow.runtime.runs.manager import RunManager
    from deerflow.runtime.runs.store.memory import MemoryRunStore
    from deerflow.runtime.stream_bridge.memory import MemoryStreamBridge
    from deerflow.sandbox.sandbox_provider import reset_sandbox_provider, shutdown_sandbox_provider

    reset_sandbox_provider()

    cfg = get_app_config()
    await init_engine_from_config(cfg.database)
    sf = get_session_factory()
    if sf is None:
        logger.error("No SQL session factory (memory backend?). Cannot poll async_tasks.")
        return 1

    repo = AsyncTaskRepository(sf)
    bridge = MemoryStreamBridge()
    run_manager = RunManager(store=MemoryRunStore())

    set_async_task_handles(
        AsyncTaskHandles(
            repo=repo,
            bridge=bridge,
            run_manager=run_manager,
            run_context_factory=lambda: MagicMock(),
        )
    )

    app = FastAPI()
    app.state = SimpleNamespace(async_task_repo=repo)

    now = datetime.now(UTC)
    async with sf() as session:
        res = await session.execute(
            sa_update(AsyncTaskRow)
            .where(
                AsyncTaskRow.poll_command.is_not(None),
                AsyncTaskRow.status.in_(("queued", "running")),
            )
            .values(next_poll_at=now - timedelta(seconds=30))
        )
        bumped = res.rowcount or 0
        await session.commit()
    logger.info("Bumped next_poll_at for %d active poll row(s).", bumped)

    due = await repo.iter_due_poll_tasks(limit=32)
    if not due:
        logger.info("No due poll tasks (skip).")
        set_async_task_handles(None)
        await close_engine()
        shutdown_sandbox_provider()
        return 0

    for row in due:
        logger.info("Polling task_id=%s thread=%s kind=%s", row.id, row.thread_id, row.task_kind)
        await _run_one_poll(app, row)
        reloaded = await repo.load(row.id)
        if reloaded:
            logger.info(
                "After poll: status=%s next_poll_at=%s attempts=%s",
                reloaded.status,
                reloaded.next_poll_at,
                reloaded.attempts,
            )

    set_async_task_handles(None)
    await close_engine()
    shutdown_sandbox_provider()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

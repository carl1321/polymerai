# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Insert async_tasks rows from workflow run_skill (not conversation middleware)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from deerflow.runtime.async_tasks.envelope import resolve_submit_envelope

logger = logging.getLogger(__name__)


async def insert_workflow_async_task(
    repo: Any,
    *,
    user_id: str,
    workflow_run_id: str,
    workflow_node_id: str,
    source_tool_call_id: str,
    envelope: dict[str, Any],
    thread_id: str | None = None,
) -> Any | None:
    """Persist async_tasks row for a workflow detach submit."""
    poll_raw = envelope.get("poll_command")
    poll_command = poll_raw.strip() if isinstance(poll_raw, str) else None
    poll_interval = int(envelope.get("poll_interval_seconds") or 300)
    poll_interval = max(30, min(poll_interval, 300))
    first_delay = max(0, int(envelope.get("first_poll_delay_seconds") or 15))
    now = datetime.now(UTC)
    next_poll = now + timedelta(seconds=first_delay)
    async_thread = thread_id or f"wf:{workflow_run_id}"

    from deerflow.persistence.async_task.model import AsyncTaskRow

    row = AsyncTaskRow(
        id=uuid.uuid4(),
        user_id=str(user_id),
        thread_id=async_thread,
        source_run_id=str(workflow_run_id),
        source_tool_call_id=source_tool_call_id,
        task_kind=str(envelope.get("task_kind") or "custom"),
        display_name=envelope.get("display_name") if isinstance(envelope.get("display_name"), str) else None,
        status="queued" if poll_command else "awaiting_callback",
        payload=dict(envelope),
        poll_command=poll_command,
        poll_interval_seconds=poll_interval,
        next_poll_at=next_poll if poll_command else now + timedelta(seconds=poll_interval or 604800),
        external_ref=str(envelope["external_ref"]) if envelope.get("external_ref") is not None else None,
        callback_secret=str(envelope["callback_secret"]) if envelope.get("callback_secret") else None,
        workflow_run_id=uuid.UUID(str(workflow_run_id)),
        workflow_node_id=workflow_node_id,
        created_at=now,
        updated_at=now,
    )
    async with repo._sf() as session:
        session.add(row)
        try:
            from sqlalchemy.exc import IntegrityError

            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(row)
        return row


def capture_envelope_from_tool_output(tool_output: str) -> dict[str, Any] | None:
    """Parse DeerFlow submit envelope from tool stdout line or workflow run_skill JSON."""
    env = resolve_submit_envelope(tool_output)
    if env:
        return env
    if not tool_output or not isinstance(tool_output, str):
        return None
    try:
        payload = json.loads(tool_output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    nested = payload.get("async_envelope")
    if isinstance(nested, dict) and nested.get("status") == "submitted" and nested.get("task_kind"):
        return nested
    if payload.get("status") == "submitted" and payload.get("task_kind"):
        return payload
    return None


def capture_envelope_from_tool_outputs(tool_outputs: list[str]) -> dict[str, Any] | None:
    for text in reversed(tool_outputs):
        env = capture_envelope_from_tool_output(text)
        if env:
            return env
    return None


async def init_workflow_async_task_support() -> None:
    """Initialize SQL async_task repo for workflow worker (gateway sets this at startup)."""
    try:
        from deerflow.runtime.async_tasks.registry import (
            AsyncTaskHandles,
            get_async_task_handles,
            set_async_task_handles,
        )

        existing = get_async_task_handles()
        if existing and existing.repo:
            return
        from deerflow.config.app_config import get_app_config
        from deerflow.persistence.async_task import AsyncTaskRepository
        from deerflow.persistence.engine import get_session_factory, init_engine_from_config

        cfg = get_app_config()
        await init_engine_from_config(cfg.database)
        sf = get_session_factory()
        if sf is None:
            logger.warning("Workflow worker: no SQL session factory for async_tasks")
            return
        repo = AsyncTaskRepository(sf)
        set_async_task_handles(
            AsyncTaskHandles(
                repo=repo,
                bridge=None,
                run_manager=None,
                run_context_factory=None,
            )
        )
        logger.info("Workflow worker: async_task repo initialized")
    except Exception as exc:
        logger.warning("Workflow async_task support init failed: %s", exc, exc_info=True)


def get_workflow_async_task_repo() -> Any | None:
    """Async task repo on gateway (preferred) or workflow worker fallback."""
    try:
        from deerflow.runtime.async_tasks.registry import get_async_task_handles

        handles = get_async_task_handles()
        if handles and handles.repo:
            return handles.repo
    except Exception:
        pass
    try:
        from deerflow.persistence.engine import get_session_factory
        from deerflow.persistence.async_task import AsyncTaskRepository

        sf = get_session_factory()
        if sf is not None:
            return AsyncTaskRepository(sf)
    except Exception:
        logger.debug("Workflow async_task repo unavailable", exc_info=True)
    return None

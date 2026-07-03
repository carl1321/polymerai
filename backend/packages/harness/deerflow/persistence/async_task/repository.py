"""async_tasks repository — INSERT / claim / UPDATE."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.async_task.model import AsyncTaskRow

_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timeout"})


class AsyncTaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def insert_from_capture(
        self,
        *,
        user_id: str,
        thread_id: str,
        source_run_id: str,
        source_tool_call_id: str,
        envelope: dict[str, Any],
    ) -> AsyncTaskRow | None:
        poll_raw = envelope.get("poll_command")
        poll_command = poll_raw.strip() if isinstance(poll_raw, str) else None
        poll_interval = int(envelope.get("poll_interval_seconds") or 1800)
        first_delay = max(0, int(envelope.get("first_poll_delay_seconds") or 0))

        now = datetime.now(UTC)
        next_poll = now + timedelta(seconds=first_delay)

        if poll_command:
            row_status = "queued"
            next_poll_at = next_poll
        else:
            row_status = "awaiting_callback"
            ttl = poll_interval if poll_interval > 0 else 604800
            next_poll_at = now + timedelta(seconds=ttl)

        row = AsyncTaskRow(
            id=uuid.uuid4(),
            user_id=user_id,
            thread_id=thread_id,
            source_run_id=source_run_id,
            source_tool_call_id=source_tool_call_id,
            task_kind=str(envelope.get("task_kind") or "custom"),
            display_name=envelope.get("display_name") if isinstance(envelope.get("display_name"), str) else None,
            status=row_status,
            payload=dict(envelope),
            poll_command=poll_command,
            poll_interval_seconds=poll_interval,
            next_poll_at=next_poll_at,
            external_ref=str(envelope["external_ref"]) if envelope.get("external_ref") is not None else None,
            callback_secret=str(envelope["callback_secret"]) if envelope.get("callback_secret") else None,
            created_at=now,
            updated_at=now,
        )
        async with self._sf() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
            await session.refresh(row)
            return row

    async def count_active_by_thread(self, thread_id: str) -> int:
        """Count non-terminal async_tasks rows (poll or webhook wait) for *thread_id*."""
        stmt = select(func.count(AsyncTaskRow.id)).where(
            AsyncTaskRow.thread_id == thread_id,
            AsyncTaskRow.status.in_(("queued", "running", "awaiting_callback")),
        )
        async with self._sf() as session:
            n = await session.scalar(stmt)
            return int(n or 0)

    async def list_by_thread_for_user(
        self,
        thread_id: str,
        user_id: str,
        *,
        limit: int = 50,
    ) -> list[AsyncTaskRow]:
        stmt = select(AsyncTaskRow).where(AsyncTaskRow.thread_id == thread_id, AsyncTaskRow.user_id == user_id).order_by(AsyncTaskRow.created_at.desc()).limit(max(1, min(limit, 200)))
        async with self._sf() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def iter_due_poll_tasks(self, *, limit: int = 32) -> list[AsyncTaskRow]:
        """Rows eligible for sandbox poll (non-terminal, poll_command set, next_poll_at due)."""
        now = datetime.now(UTC)
        stmt = (
            select(AsyncTaskRow)
            .where(
                AsyncTaskRow.poll_command.is_not(None),
                AsyncTaskRow.status.in_(("queued", "running")),
                AsyncTaskRow.next_poll_at.is_not(None),
                AsyncTaskRow.next_poll_at <= now,
            )
            .order_by(AsyncTaskRow.next_poll_at.asc())
            .limit(limit)
        )
        async with self._sf() as session:
            bind = session.bind
            dialect = getattr(getattr(bind, "dialect", None), "name", "") if bind is not None else ""
            if dialect == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            async with session.begin():
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
                for r in rows:
                    session.expunge(r)
            return rows

    async def apply_poll_success_update(
        self,
        task_id: uuid.UUID,
        *,
        previous_status: str,
        new_status: str,
        payload_patch: dict[str, Any] | None,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> AsyncTaskRow | None:
        now = datetime.now(UTC)
        async with self._sf() as session:
            row = await session.get(AsyncTaskRow, task_id)
            if row is None:
                return None
            if payload_patch:
                merged = dict(row.payload or {})
                merged.update(payload_patch)
                row.payload = merged
            row.status = new_status
            row.updated_at = now
            row.heartbeat_at = now
            row.attempts = 0
            if new_status in _TERMINAL:
                row.finished_at = now
                row.next_poll_at = None
                if result is not None:
                    row.result = result
                if error is not None:
                    row.error = error
            else:
                interval = max(1, row.poll_interval_seconds)
                cap_raw = os.environ.get("DEER_FLOW_ASYNC_TASK_POLL_INTERVAL_CAP", "300").strip()
                if cap_raw.isdigit():
                    cap = int(cap_raw)
                    if cap > 0:
                        interval = min(interval, cap)
                row.next_poll_at = now + timedelta(seconds=interval)
            await session.commit()
            await session.refresh(row)
            return row

    async def load(self, task_id: uuid.UUID) -> AsyncTaskRow | None:
        async with self._sf() as session:
            return await session.get(AsyncTaskRow, task_id)

    async def increment_poll_failure(self, task_id: uuid.UUID) -> AsyncTaskRow | None:
        async with self._sf() as session:
            row = await session.get(AsyncTaskRow, task_id)
            if row is None:
                return None
            row.attempts += 1
            now = datetime.now(UTC)
            row.updated_at = now
            if row.attempts >= row.max_attempts:
                row.status = "failed"
                row.finished_at = now
                row.next_poll_at = None
                row.error = {"code": "poll_exhausted", "message": "Sandbox poll command failed repeatedly"}
            else:
                base = max(1, row.poll_interval_seconds)
                retry = min(180, max(20, base // 15))
                row.next_poll_at = now + timedelta(seconds=retry)
            await session.commit()
            await session.refresh(row)
            return row

    async def mark_terminal_followup(
        self,
        task_id: uuid.UUID,
        *,
        resume_run_id: str,
    ) -> bool:
        async with self._sf() as session:
            res = await session.execute(
                update(AsyncTaskRow)
                .where(AsyncTaskRow.id == task_id, AsyncTaskRow.terminal_followup_done.is_(False))
                .values(
                    terminal_followup_done=True,
                    resume_run_id=resume_run_id,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return res.rowcount > 0

    async def list_terminal_unfollowed(self, *, limit: int = 50) -> list[AsyncTaskRow]:
        stmt = (
            select(AsyncTaskRow)
            .where(
                AsyncTaskRow.status.in_(tuple(_TERMINAL)),
                AsyncTaskRow.terminal_followup_done.is_(False),
            )
            .order_by(AsyncTaskRow.updated_at.asc())
            .limit(limit)
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_webhook_wait_overdue(self, *, limit: int = 32) -> list[AsyncTaskRow]:
        now = datetime.now(UTC)
        stmt = (
            select(AsyncTaskRow)
            .where(
                AsyncTaskRow.status == "awaiting_callback",
                AsyncTaskRow.next_poll_at.is_not(None),
                AsyncTaskRow.next_poll_at <= now,
            )
            .order_by(AsyncTaskRow.next_poll_at.asc())
            .limit(limit)
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def mark_webhook_timeout(self, task_id: uuid.UUID) -> AsyncTaskRow | None:
        now = datetime.now(UTC)
        async with self._sf() as session:
            row = await session.get(AsyncTaskRow, task_id)
            if row is None or row.status != "awaiting_callback":
                return None
            row.status = "timeout"
            row.finished_at = now
            row.next_poll_at = None
            row.error = {"code": "webhook_timeout", "message": "No callback before deadline"}
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return row

    async def apply_webhook_update(
        self,
        task_id: uuid.UUID,
        *,
        callback_secret: str | None,
        new_status: str,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> AsyncTaskRow | None:
        now = datetime.now(UTC)
        async with self._sf() as session:
            row = await session.get(AsyncTaskRow, task_id)
            if row is None:
                return None
            if row.status != "awaiting_callback":
                return None
            if new_status not in _TERMINAL:
                return None
            if row.callback_secret and callback_secret != row.callback_secret:
                return None
            row.status = new_status
            row.updated_at = now
            row.finished_at = now
            row.next_poll_at = None
            if result is not None:
                row.result = result
            if error is not None:
                row.error = error
            await session.commit()
            await session.refresh(row)
            return row

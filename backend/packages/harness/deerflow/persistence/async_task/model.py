"""ORM model for async_tasks — table created only via PostgreSQL DDL scripts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class AsyncTaskRow(Base):
    __tablename__ = "async_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64))
    source_tool_call_id: Mapped[str | None] = mapped_column(String(128))
    task_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    poll_command: Mapped[str | None] = mapped_column(Text())
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1800")
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_ref: Mapped[str | None] = mapped_column(String(512))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_run_id: Mapped[str | None] = mapped_column(String(64))
    terminal_followup_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    callback_secret: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # FK to workflow_runs(id) is enforced by PostgreSQL DDL (init_app_database / async_tasks_pg.sql),
    # not SQLAlchemy — workflow_runs has no ORM model on this Base.
    workflow_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    workflow_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

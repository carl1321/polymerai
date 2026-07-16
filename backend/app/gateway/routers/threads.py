"""Thread CRUD, state, and history endpoints.

Combines the existing thread-local filesystem cleanup with LangGraph
Platform-compatible thread management backed by the checkpointer.

Channel values returned in state responses are serialized through
:func:`deerflow.runtime.serialization.serialize_channel_values` to
ensure LangChain message objects are converted to JSON-safe dicts
matching the LangGraph Platform wire format expected by the
``useStream`` React hook.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.checkpoint.base import empty_checkpoint
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import get_checkpointer, get_run_event_store, get_run_manager, get_run_store, get_store, get_thread_store
from deerflow.config.paths import Paths, get_paths
from deerflow.runtime import serialize_channel_values
from deerflow.runtime.user_context import get_effective_user_id
from deerflow.utils.time import coerce_iso, now_iso

try:
    from extensions.auth.dependencies import CurrentUser, get_current_user_optional
except Exception:  # pragma: no cover
    CurrentUser = Any  # type: ignore[misc,assignment]

    async def get_current_user_optional():  # type: ignore[no-redef]
        return None

# ---------------------------------------------------------------------------
# Store namespace
# ---------------------------------------------------------------------------

THREADS_NS: tuple[str, ...] = ("threads",)
"""Namespace used by the Store for thread metadata records."""
THREAD_TOMBSTONES_NS: tuple[str, ...] = ("thread_tombstones",)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class ThreadDeleteResponse(BaseModel):
    """Response model for thread cleanup."""

    success: bool
    message: str


class ThreadResponse(BaseModel):
    """Response model for a single thread."""

    thread_id: str = Field(description="Unique thread identifier")
    status: str = Field(default="idle", description="Thread status: idle, busy, interrupted, error")
    created_at: str = Field(default="", description="ISO timestamp")
    updated_at: str = Field(default="", description="ISO timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    values: dict[str, Any] = Field(default_factory=dict, description="Current state channel values")
    interrupts: dict[str, Any] = Field(default_factory=dict, description="Pending interrupts")


class ThreadCreateRequest(BaseModel):
    """Request body for creating a thread."""

    thread_id: str | None = Field(default=None, description="Optional thread ID (auto-generated if omitted)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Initial metadata")


class ThreadSearchRequest(BaseModel):
    """Request body for searching threads."""

    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata filter (exact match)")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    status: str | None = Field(default=None, description="Filter by thread status")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata_filters(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Reject filter entries the SQL backend cannot compile.

        Enforces consistent behaviour across SQL and memory backends.
        See ``deerflow.persistence.json_compat`` for the shared validators.
        """
        if not v:
            return v
        from deerflow.persistence.json_compat import validate_metadata_filter_key, validate_metadata_filter_value

        bad_entries: list[str] = []
        for key, value in v.items():
            if not validate_metadata_filter_key(key):
                bad_entries.append(f"{key!r} (unsafe key)")
            elif not validate_metadata_filter_value(value):
                bad_entries.append(f"{key!r} (unsupported value type {type(value).__name__})")
        if bad_entries:
            raise ValueError(f"Invalid metadata filter entries: {', '.join(bad_entries)}")
        return v


class ThreadStateResponse(BaseModel):
    """Response model for thread state."""

    values: dict[str, Any] = Field(default_factory=dict, description="Current channel values")
    next: list[str] = Field(default_factory=list, description="Next tasks to execute")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Checkpoint metadata")
    checkpoint: dict[str, Any] = Field(default_factory=dict, description="Checkpoint info")
    checkpoint_id: str | None = Field(default=None, description="Current checkpoint ID")
    parent_checkpoint_id: str | None = Field(default=None, description="Parent checkpoint ID")
    created_at: str | None = Field(default=None, description="Checkpoint timestamp")
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="Interrupted task details")


class ThreadPatchRequest(BaseModel):
    """Request body for patching thread metadata."""

    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata to merge")


class ThreadStateUpdateRequest(BaseModel):
    """Request body for updating thread state (human-in-the-loop resume)."""

    values: dict[str, Any] | None = Field(default=None, description="Channel values to merge")
    checkpoint_id: str | None = Field(default=None, description="Checkpoint to branch from")
    checkpoint: dict[str, Any] | None = Field(default=None, description="Full checkpoint object")
    as_node: str | None = Field(default=None, description="Node identity for the update")


class HistoryEntry(BaseModel):
    """Single checkpoint history entry."""

    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    next: list[str] = Field(default_factory=list)


class ThreadHistoryRequest(BaseModel):
    """Request body for checkpoint history."""

    limit: int = Field(default=10, ge=1, le=100, description="Maximum entries")
    before: str | None = Field(default=None, description="Cursor for pagination")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THREAD_OWNER_KEY = "user_id"


def _delete_thread_data(thread_id: str, user_id: str | None = None, paths: Paths | None = None) -> ThreadDeleteResponse:
    """Delete local persisted filesystem data for a thread."""
    path_manager = paths or get_paths()
    try:
        if user_id is None:
            path_manager.delete_thread_dir(thread_id)
        else:
            path_manager.delete_thread_dir(thread_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError:
        # Not critical — thread data may not exist on disk
        logger.debug("No local thread data to delete for %s", thread_id)
        return ThreadDeleteResponse(success=True, message=f"No local data for {thread_id}")
    except Exception as exc:
        logger.exception("Failed to delete thread data for %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete local thread data.") from exc

    logger.info("Deleted local thread data for %s", thread_id)
    return ThreadDeleteResponse(success=True, message=f"Deleted local thread data for {thread_id}")


async def _store_get(store, thread_id: str) -> dict | None:
    """Fetch a thread record from the Store; returns ``None`` if absent."""
    item = await store.aget(THREADS_NS, thread_id)
    return item.value if item is not None else None


async def _store_put(store, record: dict) -> None:
    """Write a thread record to the Store."""
    await store.aput(THREADS_NS, record["thread_id"], record)


async def _store_upsert(store, thread_id: str, *, metadata: dict | None = None, values: dict | None = None) -> None:
    """Create or refresh a thread record in the Store.

    On creation the record is written with ``status="idle"``.  On update only
    ``updated_at`` (and optionally ``metadata`` / ``values``) are changed so
    that existing fields are preserved.

    ``values`` carries the agent-state snapshot exposed to the frontend
    (currently just ``{"title": "..."}``).
    """
    now = time.time()
    existing = await _store_get(store, thread_id)
    if existing is None:
        await _store_put(
            store,
            {
                "thread_id": thread_id,
                "status": "idle",
                "created_at": now,
                "updated_at": now,
                "metadata": metadata or {},
                "values": values or {},
            },
        )
    else:
        val = dict(existing)
        val["updated_at"] = now
        if metadata:
            val.setdefault("metadata", {}).update(metadata)
        if values:
            val.setdefault("values", {}).update(values)
        await _store_put(store, val)


async def _store_mark_tombstone(store, thread_id: str, user_id: str) -> None:
    if store is None:
        return
    await store.aput(
        THREAD_TOMBSTONES_NS,
        f"{user_id}:{thread_id}",
        {"thread_id": thread_id, "user_id": user_id, "deleted_at": time.time()},
    )


def _require_user(user: CurrentUser | None, request: Request | None = None) -> CurrentUser:
    if user is None and request is not None:
        user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _user_id_str(user: CurrentUser) -> str:
    uid = getattr(user, "id", None)
    return str(uid) if uid is not None else ""


def _owner_from_store_record(record: dict | None) -> str | None:
    if not record:
        return None
    meta = record.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    owner = meta.get(_THREAD_OWNER_KEY)
    if isinstance(owner, str) and owner.strip():
        return owner.strip()
    return None


def _strip_reserved_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(metadata or {})
    cleaned.pop(_THREAD_OWNER_KEY, None)
    return cleaned


def _owner_from_checkpoint_tuple(checkpoint_tuple) -> str | None:
    if checkpoint_tuple is None:
        return None
    cfg = getattr(checkpoint_tuple, "config", {}) or {}
    owner = (cfg.get("configurable", {}) or {}).get(_THREAD_OWNER_KEY)
    if isinstance(owner, str) and owner.strip():
        return owner.strip()
    meta = getattr(checkpoint_tuple, "metadata", {}) or {}
    if isinstance(meta, dict):
        owner2 = meta.get(_THREAD_OWNER_KEY)
        if isinstance(owner2, str) and owner2.strip():
            return owner2.strip()
    return None


def _assert_thread_owner(owner_id: str | None, user: CurrentUser) -> None:
    # Do not leak thread existence across users.
    if not owner_id or owner_id != _user_id_str(user):
        raise HTTPException(status_code=404, detail="Thread not found")


def _requestor_owns_thread(
    user: CurrentUser,
    *,
    checkpoint_owner: str | None,
    store_owner: str | None,
) -> bool:
    """True if the authenticated user owns this thread by checkpoint or Store metadata."""
    uid = _user_id_str(user)
    if not uid:
        return False
    if checkpoint_owner and checkpoint_owner.strip() == uid:
        return True
    if store_owner and store_owner.strip() == uid:
        return True
    return False


def _derive_thread_status(checkpoint_tuple) -> str:
    """Derive thread status from checkpoint metadata."""
    if checkpoint_tuple is None:
        return "idle"
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []

    # Check for error in pending writes
    for pw in pending_writes:
        if len(pw) >= 2 and pw[1] == "__error__":
            return "error"

    # Check for pending next tasks (indicates interrupt)
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return "interrupted"

    return "idle"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.delete("/{thread_id}", response_model=ThreadDeleteResponse)
async def delete_thread_data(
    thread_id: str,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadDeleteResponse:
    """Delete local persisted filesystem data for a thread.

    Cleans DeerFlow-managed thread directories, removes checkpoint data,
    and removes the thread record from the Store.
    """
    user = _require_user(current_user, request)
    thread_store = get_thread_store(request)
    run_store = get_run_store(request)
    run_event_store = get_run_event_store(request)
    run_manager = get_run_manager(request)
    owner_uid = _user_id_str(user)
    thread_meta = await thread_store.get(thread_id, user_id=owner_uid)
    if thread_meta is None:
        thread_meta = await thread_store.get(thread_id, user_id=None)
    if thread_meta is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    store = get_store(request)
    owner_id = thread_meta.get("user_id")

    checkpointer = getattr(request.app.state, "checkpointer", None)
    if not owner_id and checkpointer is not None:
        try:
            cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint_tuple = await checkpointer.aget_tuple(cfg)
            owner_id = _owner_from_checkpoint_tuple(checkpoint_tuple)
        except Exception:
            owner_id = None

    if owner_id:
        _assert_thread_owner(owner_id, user)

    # Clean local filesystem
    delete_user_id = owner_id or get_effective_user_id()
    response = _delete_thread_data(thread_id, delete_user_id)

    # Remove from Store (best-effort)
    if store is not None:
        try:
            await _store_mark_tombstone(store, thread_id, _user_id_str(user))
            await store.adelete(THREADS_NS, thread_id)
        except Exception:
            logger.debug("Could not delete store record for thread %s (not critical)", thread_id)

    # Remove run metadata + run events for this thread (best-effort)
    try:
        while True:
            run_rows = await run_store.list_by_thread(thread_id, user_id=None, limit=200)
            if not run_rows:
                break
            for row in run_rows:
                run_id = row.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    continue
                await run_store.delete(run_id, user_id=None)
                await run_manager.cleanup(run_id, delay=0)
    except Exception:
        logger.debug("Could not delete run metadata for thread %s (not critical)", thread_id, exc_info=True)

    try:
        await run_event_store.delete_by_thread(thread_id, user_id=None)
    except Exception:
        logger.debug("Could not delete run events for thread %s (not critical)", thread_id, exc_info=True)

    try:
        await thread_store.delete(thread_id, user_id=None)
    except Exception:
        logger.debug("Could not delete threads_meta record for thread %s (not critical)", thread_id)

    # Remove checkpoints (best-effort)
    if checkpointer is not None:
        try:
            if hasattr(checkpointer, "adelete_thread"):
                await checkpointer.adelete_thread(thread_id)
        except Exception:
            logger.debug("Could not delete checkpoints for thread %s (not critical)", thread_id)

    return response


@router.post("", response_model=ThreadResponse)
async def create_thread(
    body: ThreadCreateRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadResponse:
    """Create a new thread.

    The thread record is written to the Store (for fast listing) and an
    empty checkpoint is written to the checkpointer (for state reads).
    Idempotent: returns the existing record when ``thread_id`` already exists.
    """
    thread_store = get_thread_store(request)
    store = get_store(request)
    checkpointer = get_checkpointer(request)
    thread_id = body.thread_id or str(uuid.uuid4())
    now = now_iso()
    user = _require_user(current_user, request)

    metadata = _strip_reserved_metadata(body.metadata)
    metadata[_THREAD_OWNER_KEY] = _user_id_str(user)

    existing_meta = await thread_store.get(thread_id, user_id=_user_id_str(user))
    if existing_meta is not None:
        values: dict[str, Any] = {}
        display_name = existing_meta.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            values["title"] = display_name
        return ThreadResponse(
            thread_id=thread_id,
            status=existing_meta.get("status", "idle"),
            created_at=coerce_iso(existing_meta.get("created_at", "")),
            updated_at=coerce_iso(existing_meta.get("updated_at", "")),
            metadata=existing_meta.get("metadata", {}),
            values=values,
        )

    try:
        initial_title = metadata.get("title") if isinstance(metadata.get("title"), str) else None
        await thread_store.create(
            thread_id,
            user_id=_user_id_str(user),
            display_name=initial_title,
            metadata=metadata,
        )
    except Exception:
        logger.exception("Failed to write thread %s to thread metadata store", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread")

    if store is not None:
        try:
            await _store_put(
                store,
                {
                    "thread_id": thread_id,
                    "status": "idle",
                    "created_at": now,
                    "updated_at": now,
                    "metadata": metadata,
                    "values": {},
                },
            )
        except Exception:
            logger.warning("Failed to mirror thread %s to store cache (non-fatal)", thread_id)

    # Write an empty checkpoint so state endpoints work immediately
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        ckpt_metadata = {
            "step": -1,
            "source": "input",
            "writes": None,
            "parents": {},
            **metadata,
            "created_at": now,
        }
        await checkpointer.aput(config, empty_checkpoint(), ckpt_metadata, {})
    except Exception:
        logger.exception("Failed to create checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread")

    logger.info("Thread created: %s", thread_id)
    return ThreadResponse(
        thread_id=thread_id,
        status="idle",
        created_at=now,
        updated_at=now,
        metadata=metadata,
    )


@router.post("/search", response_model=list[ThreadResponse])
async def search_threads(
    body: ThreadSearchRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> list[ThreadResponse]:
    """Search and list threads from thread metadata store."""
    from deerflow.persistence.thread_meta import InvalidMetadataFilterError

    user = _require_user(current_user, request)
    thread_store = get_thread_store(request)
    try:
        rows = await thread_store.search(
            metadata=body.metadata or None,
            status=body.status,
            limit=body.limit,
            offset=body.offset,
            user_id=_user_id_str(user),
        )
    except InvalidMetadataFilterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.warning("Thread metadata search failed", exc_info=True)
        return []

    results: list[ThreadResponse] = []
    for row in rows:
        values: dict[str, Any] = {}
        display_name = row.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            values["title"] = display_name
        else:
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            title_from_meta = md.get("title")
            if isinstance(title_from_meta, str) and title_from_meta.strip():
                values["title"] = title_from_meta
        results.append(
            ThreadResponse(
                thread_id=row.get("thread_id", ""),
                status=row.get("status", "idle"),
                created_at=coerce_iso(row.get("created_at", "")),
                updated_at=coerce_iso(row.get("updated_at", "")),
                metadata=row.get("metadata", {}),
                values=values,
            )
        )
    return results


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def patch_thread(
    thread_id: str,
    body: ThreadPatchRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadResponse:
    """Merge metadata into a thread record."""
    user = _require_user(current_user, request)
    thread_store = get_thread_store(request)
    store = get_store(request)
    owner = _user_id_str(user)
    record = await thread_store.get(thread_id, user_id=owner)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    now = time.time()
    merged_metadata = dict(record.get("metadata", {}))
    merged_metadata.update(_strip_reserved_metadata(body.metadata))
    merged_metadata[_THREAD_OWNER_KEY] = owner

    try:
        await thread_store.update_metadata(thread_id, merged_metadata, user_id=owner)
        if store is not None:
            store_record = await _store_get(store, thread_id)
            if store_record is not None:
                updated_store = dict(store_record)
                updated_store.setdefault("metadata", {}).update(merged_metadata)
                updated_store["updated_at"] = now
                await _store_put(store, updated_store)
    except Exception:
        logger.exception("Failed to patch thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to update thread")

    return ThreadResponse(
        thread_id=thread_id,
        status=record.get("status", "idle"),
        created_at=coerce_iso(record.get("created_at", "")),
        updated_at=coerce_iso(now),
        metadata=merged_metadata,
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadResponse:
    """Get thread info.

    Reads metadata from threads_meta and derives execution status from
    the checkpointer.
    """
    user = _require_user(current_user, request)
    thread_store = get_thread_store(request)
    checkpointer = get_checkpointer(request)

    record = await thread_store.get(thread_id, user_id=_user_id_str(user))

    # Derive accurate status from the checkpointer
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread")

    if record is None and checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # Legacy threads may exist only in the checkpointer (pre thread_meta adoption).
    if record is None and checkpoint_tuple is not None:
        ckpt_meta = getattr(checkpoint_tuple, "metadata", {}) or {}
        record = {
            "thread_id": thread_id,
            "status": "idle",
            "created_at": coerce_iso(ckpt_meta.get("created_at", "")),
            "updated_at": coerce_iso(ckpt_meta.get("updated_at", ckpt_meta.get("created_at", ""))),
            "metadata": {k: v for k, v in ckpt_meta.items() if k not in ("created_at", "updated_at", "step", "source", "writes", "parents")},
        }

    status = _derive_thread_status(checkpoint_tuple) if checkpoint_tuple is not None else record.get("status", "idle")
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {} if checkpoint_tuple is not None else {}
    channel_values = checkpoint.get("channel_values", {})
    if not channel_values:
        display_name = record.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            channel_values = {"title": display_name}

    return ThreadResponse(
        thread_id=thread_id,
        status=status,
        created_at=coerce_iso(record.get("created_at", "")),
        updated_at=coerce_iso(record.get("updated_at", "")),
        metadata=record.get("metadata", {}),
        values=serialize_channel_values(channel_values),
    )


@router.get("/{thread_id}/state", response_model=ThreadStateResponse)
async def get_thread_state(
    thread_id: str,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadStateResponse:
    """Get the latest state snapshot for a thread.

    Channel values are serialized to ensure LangChain message objects
    are converted to JSON-safe dicts.
    """
    user = _require_user(current_user, request)
    thread_store = get_thread_store(request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)
    record = await _store_get(store, thread_id) if store is not None else None
    store_owner = _owner_from_store_record(record)
    thread_meta = await thread_store.get(thread_id, user_id=_user_id_str(user))

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        if thread_meta is None:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        fallback_values: dict[str, Any] = {}
        display_name = thread_meta.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            fallback_values["title"] = display_name
        return ThreadStateResponse(
            values=fallback_values,
            next=[],
            metadata=thread_meta.get("metadata", {}),
            checkpoint={},
            checkpoint_id=None,
            parent_checkpoint_id=None,
            created_at=str(thread_meta.get("created_at", "")),
            tasks=[],
        )

    ck_owner = _owner_from_checkpoint_tuple(checkpoint_tuple)
    if not _requestor_owns_thread(user, checkpoint_owner=ck_owner, store_owner=store_owner):
        raise HTTPException(status_code=404, detail="Thread not found")

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
    checkpoint_id = None
    ckpt_config = getattr(checkpoint_tuple, "config", {})
    if ckpt_config:
        checkpoint_id = ckpt_config.get("configurable", {}).get("checkpoint_id")

    channel_values = checkpoint.get("channel_values", {})

    parent_config = getattr(checkpoint_tuple, "parent_config", None)
    parent_checkpoint_id = None
    if parent_config:
        parent_checkpoint_id = parent_config.get("configurable", {}).get("checkpoint_id")

    tasks_raw = getattr(checkpoint_tuple, "tasks", []) or []
    next_tasks = [t.name for t in tasks_raw if hasattr(t, "name")]
    tasks = [{"id": getattr(t, "id", ""), "name": getattr(t, "name", "")} for t in tasks_raw]

    return ThreadStateResponse(
        values=serialize_channel_values(channel_values),
        next=next_tasks,
        metadata=metadata,
        checkpoint={"id": checkpoint_id, "ts": coerce_iso(metadata.get("created_at", ""))},
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=parent_checkpoint_id,
        created_at=coerce_iso(metadata.get("created_at", "")),
        tasks=tasks,
    )


@router.post("/{thread_id}/state", response_model=ThreadStateResponse)
async def update_thread_state(
    thread_id: str,
    body: ThreadStateUpdateRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> ThreadStateResponse:
    """Update thread state (e.g. for human-in-the-loop resume or title rename).

    Writes a new checkpoint that merges *body.values* into the latest
    channel values, then syncs any updated ``title`` to the LangGraph Store
    and ``threads_meta.display_name`` (via :meth:`ThreadMetaStore.update_display_name`)
    so ``/threads/search`` — which reads ThreadMetaStore first — stays consistent.
    """
    user = _require_user(current_user, request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)

    # checkpoint_ns must be present in the config for aput — default to ""
    # (the root graph namespace).  checkpoint_id is optional; omitting it
    # fetches the latest checkpoint for the thread.
    read_config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
        }
    }
    if body.checkpoint_id:
        read_config["configurable"]["checkpoint_id"] = body.checkpoint_id

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(read_config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    ck_owner = _owner_from_checkpoint_tuple(checkpoint_tuple)
    record = await _store_get(store, thread_id) if store is not None else None
    store_owner = _owner_from_store_record(record)
    if not _requestor_owns_thread(user, checkpoint_owner=ck_owner, store_owner=store_owner):
        raise HTTPException(status_code=404, detail="Thread not found")

    # Work on mutable copies so we don't accidentally mutate cached objects.
    checkpoint: dict[str, Any] = dict(getattr(checkpoint_tuple, "checkpoint", {}) or {})
    metadata: dict[str, Any] = dict(getattr(checkpoint_tuple, "metadata", {}) or {})
    channel_values: dict[str, Any] = dict(checkpoint.get("channel_values", {}))

    if body.values:
        channel_values.update(body.values)

    checkpoint["channel_values"] = channel_values
    metadata["updated_at"] = now_iso()
    metadata[_THREAD_OWNER_KEY] = _user_id_str(user)

    if body.as_node:
        metadata["source"] = "update"
        metadata["step"] = metadata.get("step", 0) + 1
        metadata["writes"] = {body.as_node: body.values}

    # aput requires checkpoint_ns in the config — use the same config used for the
    # read (which always includes checkpoint_ns="").  Do NOT include checkpoint_id
    # so that aput generates a fresh checkpoint ID for the new snapshot.
    write_config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
        }
    }
    try:
        new_config = await checkpointer.aput(write_config, checkpoint, metadata, {})
    except Exception:
        logger.exception("Failed to update state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to update thread state")

    new_checkpoint_id: str | None = None
    if isinstance(new_config, dict):
        new_checkpoint_id = new_config.get("configurable", {}).get("checkpoint_id")

    # Sync title to LangGraph Store and threads_meta.display_name (list API prefers display_name).
    if body.values and "title" in body.values:
        title_val = body.values["title"]
        if store is not None:
            try:
                await _store_upsert(store, thread_id, values={"title": title_val})
            except Exception:
                logger.debug("Failed to sync title to store for thread %s (non-fatal)", thread_id)
        thread_store = get_thread_store(request)
        try:
            display = title_val if isinstance(title_val, str) else str(title_val)
            await thread_store.update_display_name(thread_id, display, user_id=_user_id_str(user))
        except Exception:
            logger.debug(
                "Failed to sync display_name to thread_store for thread %s (non-fatal)",
                thread_id,
                exc_info=True,
            )

    return ThreadStateResponse(
        values=serialize_channel_values(channel_values),
        next=[],
        metadata=metadata,
        checkpoint_id=new_checkpoint_id,
        created_at=coerce_iso(metadata.get("created_at", "")),
    )


@router.post("/{thread_id}/history", response_model=list[HistoryEntry])
async def get_thread_history(
    thread_id: str,
    body: ThreadHistoryRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> list[HistoryEntry]:
    """Get checkpoint history for a thread."""
    user = _require_user(current_user, request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)
    record = await _store_get(store, thread_id) if store is not None else None
    store_owner = _owner_from_store_record(record)

    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "checkpoint_ns": ""},
    }
    if body.before:
        config["configurable"]["checkpoint_id"] = body.before

    entries: list[HistoryEntry] = []
    try:
        owner_verified = False
        async for checkpoint_tuple in checkpointer.alist(config, limit=body.limit):
            if not owner_verified:
                ck_owner = _owner_from_checkpoint_tuple(checkpoint_tuple)
                if not _requestor_owns_thread(user, checkpoint_owner=ck_owner, store_owner=store_owner):
                    raise HTTPException(status_code=404, detail="Thread not found")
                owner_verified = True
            ckpt_config = getattr(checkpoint_tuple, "config", {})
            parent_config = getattr(checkpoint_tuple, "parent_config", None)
            metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}

            checkpoint_id = ckpt_config.get("configurable", {}).get("checkpoint_id", "")
            parent_id = None
            if parent_config:
                parent_id = parent_config.get("configurable", {}).get("checkpoint_id")

            channel_values = checkpoint.get("channel_values", {})

            # Derive next tasks
            tasks_raw = getattr(checkpoint_tuple, "tasks", []) or []
            next_tasks = [t.name for t in tasks_raw if hasattr(t, "name")]

            entries.append(
                HistoryEntry(
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=parent_id,
                    metadata=metadata,
                    values=serialize_channel_values(channel_values),
                    created_at=coerce_iso(metadata.get("created_at", "")),
                    next=next_tasks,
                )
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get history for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread history")

    return entries

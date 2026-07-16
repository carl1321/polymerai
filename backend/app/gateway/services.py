"""Run lifecycle service layer.

Centralizes the business logic for creating runs, formatting SSE
frames, and consuming stream bridge events.  Router modules
(``thread_runs``, ``runs``) are thin HTTP handlers that delegate here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import convert_to_messages

from app.gateway.deps import get_checkpointer, get_run_context, get_run_manager, get_store, get_stream_bridge, get_thread_store
from deerflow.config.app_config import get_app_config
from deerflow.runtime import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    ConflictError,
    DisconnectMode,
    RunManager,
    RunRecord,
    RunStatus,
    StreamBridge,
    UnsupportedStrategyError,
    run_agent,
)
from deerflow.runtime.runs.naming import resolve_root_run_name

try:
    from extensions.auth.dependencies import CurrentUser
except Exception:  # pragma: no cover
    CurrentUser = Any  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame.

    Field order: ``event:`` -> ``data:`` -> ``id:`` (optional) -> blank line.
    This matches the LangGraph Platform wire format consumed by the
    ``useStream`` React hook and the Python ``langgraph-sdk`` SSE decoder.
    """
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


def _build_end_event_payload(record: RunRecord) -> dict[str, Any]:
    finished_dt = datetime.now(UTC)
    finished_at = finished_dt.isoformat()
    finished_at_ms = int(finished_dt.timestamp() * 1000)
    duration_ms: int | None = None

    try:
        started_dt = datetime.fromisoformat(record.created_at)
        duration_ms = max(0, int((finished_dt - started_dt).total_seconds() * 1000))
        started_at = started_dt.isoformat()
    except Exception:
        started_at = None

    payload: dict[str, Any] = {
        "finished_at": finished_at,
        "finished_at_ms": finished_at_ms,
        "duration_ms": duration_ms if duration_ms is not None else 0,
    }
    if started_at is not None:
        payload["started_at"] = started_at
    return payload


# ---------------------------------------------------------------------------
# Input / config helpers
# ---------------------------------------------------------------------------


def normalize_stream_modes(raw: list[str] | str | None) -> list[str]:
    """Normalize the stream_mode parameter to a list.

    Default matches what ``useStream`` expects: values + messages-tuple.
    """
    if raw is None:
        return ["values"]
    if isinstance(raw, str):
        return [raw]
    return raw if raw else ["values"]


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """Convert LangGraph Platform input format to LangChain state dict.

    Delegates dict→message coercion to ``langchain_core.messages.utils.convert_to_messages``
    so that ``additional_kwargs`` (e.g. uploaded-file metadata — gh #3132), ``id``,
    ``name``, and non-human roles (ai/system/tool) survive unchanged.  An earlier
    hand-rolled version only forwarded ``content`` and collapsed every role to
    ``HumanMessage``, which silently stripped frontend-supplied attachments.

    Malformed message dicts (missing ``role``/``type``/``content``, unsupported
    role, etc.) raise ``HTTPException(400)`` with the offending index, instead
    of bubbling up as a 500.  The gateway is a system boundary, so per-entry
    validation errors are the right shape for clients to retry against.
    """
    if raw_input is None:
        return {}
    messages = raw_input.get("messages")
    if messages and isinstance(messages, list):
        converted: list[Any] = []
        for index, msg in enumerate(messages):
            if isinstance(msg, BaseMessage):
                converted.append(msg)
            elif isinstance(msg, dict):
                try:
                    converted.extend(convert_to_messages([msg]))
                except (ValueError, TypeError, NotImplementedError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid message at input.messages[{index}]: {exc}",
                    ) from exc
            else:
                converted.append(msg)
        return {**raw_input, "messages": converted}
    return raw_input


_DEFAULT_ASSISTANT_ID = "lead_agent"


# Whitelist of run-context keys that the langgraph-compat layer forwards from
# ``body.context`` into the run config. ``config["context"]`` exists in
# LangGraph >=0.6, but these values must be written to both ``configurable``
# (for legacy ``_get_runtime_config`` consumers) and ``context`` because
# LangGraph >=1.1.9 no longer makes ``ToolRuntime.context`` fall back to
# ``configurable`` for consumers like ``setup_agent``.
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset(
    {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
        "agent_name",
        "is_bootstrap",
    }
)


def merge_run_context_overrides(config: dict[str, Any], context: Mapping[str, Any] | None) -> None:
    """Merge whitelisted keys from ``body.context`` into both ``config['configurable']``
    and ``config['context']`` so they are visible to legacy configurable readers and
    to LangGraph ``ToolRuntime.context`` consumers (e.g. the ``setup_agent`` tool —
    see issue #2677)."""
    if not context:
        return
    configurable = config.setdefault("configurable", {})
    runtime_context = config.setdefault("context", {})
    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in context:
            if isinstance(configurable, dict):
                configurable.setdefault(key, context[key])
            if isinstance(runtime_context, dict):
                runtime_context.setdefault(key, context[key])


def inject_authenticated_user_context(config: dict[str, Any], request: Request) -> None:
    """Stamp the authenticated user into the run context for background tools.

    Tool execution may happen after the request handler has returned, so tools
    that persist user-scoped files should not rely only on ambient ContextVars.
    The value comes from server-side auth state, never from client context.
    """

    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        return

    runtime_context = config.setdefault("context", {})
    if isinstance(runtime_context, dict):
        runtime_context["user_id"] = str(user_id)


def resolve_agent_factory(assistant_id: str | None):
    """Resolve the agent factory callable from config.

    Custom agents are implemented as ``lead_agent`` + an ``agent_name``
    injected into ``configurable`` or ``context`` — see
    :func:`build_run_config`.  All ``assistant_id`` values therefore map to the
    same factory; the routing happens inside ``make_lead_agent`` when it reads
    ``cfg["agent_name"]``.
    """
    from deerflow.agents.lead_agent.agent import make_lead_agent

    return make_lead_agent


def build_run_config(
    thread_id: str,
    request_config: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    *,
    assistant_id: str | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict for the agent.

    When *assistant_id* refers to a custom agent (anything other than
    ``"lead_agent"`` / ``None``), the name is forwarded as ``agent_name`` in
    whichever runtime options container is active: ``context`` for
    LangGraph >= 0.6.0 requests, otherwise ``configurable``.
    ``make_lead_agent`` reads this key to load the matching
    ``agents/<name>/SOUL.md`` and per-agent config — without it the agent
    silently runs as the default lead agent.

    This mirrors the channel manager's ``_resolve_run_params`` logic so that
    the LangGraph Platform-compatible HTTP API and the IM channel path behave
    identically.
    """
    config: dict[str, Any] = {"recursion_limit": 100}
    context_payload: dict[str, Any] | None = None
    if request_config:
        # LangGraph >= 0.6.0 introduced ``context`` as the preferred way to
        # pass thread-level data and rejects requests that include both
        # ``configurable`` and ``context``.  If the caller already sends
        # ``context``, honour it and skip our own ``configurable`` dict.
        if "context" in request_config:
            if "configurable" in request_config:
                logger.warning(
                    "build_run_config: client sent both 'context' and 'configurable'; preferring 'context' (LangGraph >= 0.6.0). thread_id=%s, caller_configurable keys=%s",
                    thread_id,
                    list(request_config.get("configurable", {}).keys()),
                )
            context_value = request_config["context"]
            if context_value is None:
                context = {}
            elif isinstance(context_value, Mapping):
                context = dict(context_value)
            else:
                raise ValueError("request config 'context' must be a mapping or null.")
            context_payload = context
            config["context"] = context
        else:
            configurable = {"thread_id": thread_id}
            configurable.update(request_config.get("configurable", {}))
            config["configurable"] = configurable
        for k, v in request_config.items():
            if k not in ("configurable", "context"):
                config[k] = v
    else:
        config["configurable"] = {"thread_id": thread_id}

    # Backward/interop compatibility:
    # Some downstream agent resolution paths still read `configurable`.
    # Mirror critical routing keys from `context` into `configurable` so
    # custom-agent binding (agent_id/agent_name) is deterministic.
    if isinstance(context_payload, dict):
        mirrored = config.setdefault("configurable", {"thread_id": thread_id})
        if "thread_id" not in mirrored:
            mirrored["thread_id"] = thread_id
        for key in ("agent_id", "agent_name", "model_name", "model"):
            if key in context_payload and key not in mirrored:
                mirrored[key] = context_payload[key]

    # Inject custom agent name when the caller specified a non-default assistant.
    # Honour an explicit agent_name in the active runtime options container.
    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        normalized = assistant_id.strip().lower().replace("_", "-")
        if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
            raise ValueError(f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization.")
        if "configurable" in config:
            target = config["configurable"]
        elif "context" in config:
            target = config["context"]
        else:
            target = config.setdefault("configurable", {})
        if target is not None and "agent_name" not in target:
            target["agent_name"] = normalized
        config.setdefault("run_name", resolve_root_run_name(config, normalized))
    if metadata:
        config.setdefault("metadata", {}).update(metadata)
    return config


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


def _strip_client_user_id_claims(body: Any) -> None:
    """Remove client-supplied user_id so the gateway is the only writer (Casdoor JWT ``sub`` ≠ DB UUID)."""
    ctx = getattr(body, "context", None)
    if isinstance(ctx, dict):
        ctx.pop("user_id", None)
    md = getattr(body, "metadata", None)
    if isinstance(md, dict):
        md.pop("user_id", None)
    req_cfg = getattr(body, "config", None)
    if isinstance(req_cfg, dict):
        conf = req_cfg.get("configurable")
        if isinstance(conf, dict):
            conf.pop("user_id", None)
        inner = req_cfg.get("context")
        if isinstance(inner, dict):
            inner.pop("user_id", None)


def enforce_run_user_identity(body: Any, current_user: CurrentUser | None) -> None:
    """Bind runs to the authenticated DeerFlow user; require auth when Casdoor is on.

    When authenticated, strip any client ``user_id`` — the server sets ``configurable["user_id"]``
    from ``CurrentUser.id`` so Casdoor ``sub`` and similar claims cannot desync checkpoints.
    """
    app_cfg = get_app_config()
    if app_cfg.auth.casdoor.enabled and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    if current_user is None:
        return

    canonical = str(getattr(current_user, "id", ""))
    if not canonical:
        raise HTTPException(status_code=401, detail="Authentication required")

    _strip_client_user_id_claims(body)


async def _upsert_thread_in_store(store, thread_id: str, metadata: dict | None) -> None:
    """Create or refresh the thread record in the Store.

    Called from :func:`start_run` so that threads created via the stateless
    ``/runs/stream`` endpoint (which never calls ``POST /threads``) still
    appear in ``/threads/search`` results.
    """
    # Deferred import to avoid circular import with the threads router module.
    from app.gateway.routers.threads import _store_upsert

    try:
        await _store_upsert(store, thread_id, metadata=metadata)
    except Exception:
        logger.warning("Failed to upsert thread %s in store (non-fatal)", thread_id)


async def _upsert_thread_in_thread_store(request: Request, thread_id: str, metadata: dict | None, assistant_id: str | None) -> None:
    """Create/update thread metadata row so new chats are visible in SQL first."""
    user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
    if not isinstance(user_id, str) or not user_id.strip():
        return
    owner = user_id.strip()
    thread_store = get_thread_store(request)
    existing = await thread_store.get(thread_id, user_id=owner)
    if existing is None:
        await thread_store.create(
            thread_id,
            assistant_id=assistant_id,
            user_id=owner,
            metadata=metadata or {},
        )
        return
    await thread_store.update_metadata(thread_id, metadata or {}, user_id=owner)


async def _sync_thread_title_after_run(
    run_task: asyncio.Task,
    thread_id: str,
    checkpointer: Any,
    store: Any,
) -> None:
    """Wait for *run_task* to finish, then persist the generated title to the Store.

    TitleMiddleware writes the generated title to the LangGraph agent state
    (checkpointer) but the Gateway's Store record is not updated automatically.
    This coroutine closes that gap by reading the final checkpoint after the
    run completes and syncing ``values.title`` into the Store record so that
    subsequent ``/threads/search`` responses include the correct title.

    Runs as a fire-and-forget :func:`asyncio.create_task`; failures are
    logged at DEBUG level and never propagate.
    """
    # Wait for the background run task to complete (any outcome).
    # asyncio.wait does not propagate task exceptions — it just returns
    # when the task is done, cancelled, or failed.
    await asyncio.wait({run_task})

    # Deferred import to avoid circular import with the threads router module.
    from app.gateway.routers.threads import _store_get, _store_put

    try:
        ckpt_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        ckpt_tuple = await checkpointer.aget_tuple(ckpt_config)
        if ckpt_tuple is None:
            return

        channel_values = ckpt_tuple.checkpoint.get("channel_values", {})
        title = channel_values.get("title")
        if not title:
            return

        existing = await _store_get(store, thread_id)
        if existing is None:
            return

        updated = dict(existing)
        updated.setdefault("values", {})["title"] = title
        updated["updated_at"] = time.time()
        await _store_put(store, updated)
        logger.debug("Synced title %r for thread %s", title, thread_id)
    except Exception:
        logger.debug("Failed to sync title for thread %s (non-fatal)", thread_id, exc_info=True)


def _derive_thread_status_from_checkpoint_tuple(checkpoint_tuple: Any) -> str:
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []
    for pw in pending_writes:
        if len(pw) >= 2 and pw[1] == "__error__":
            return "error"
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return "interrupted"
    return "idle"


async def backfill_threads_to_store(request: Request, *, limit: int = 500) -> int:
    """Backfill missing thread records from checkpointer to Store."""
    store = get_store(request)
    checkpointer = get_checkpointer(request)
    if store is None:
        return 0

    from app.gateway.routers.threads import THREAD_TOMBSTONES_NS, THREADS_NS

    backfilled = 0
    scanned = 0
    async for checkpoint_tuple in checkpointer.alist(None):
        if scanned >= limit:
            break
        scanned += 1
        cfg = getattr(checkpoint_tuple, "config", {}) or {}
        configurable = cfg.get("configurable", {}) or {}
        thread_id = configurable.get("thread_id")
        if not thread_id:
            continue
        if configurable.get("checkpoint_ns", ""):
            continue
        owner = configurable.get("user_id")
        if not isinstance(owner, str) or not owner.strip():
            meta = getattr(checkpoint_tuple, "metadata", {}) or {}
            candidate = meta.get("user_id")
            if isinstance(candidate, str) and candidate.strip():
                owner = candidate.strip()
        if not isinstance(owner, str) or not owner.strip():
            continue

        tombstone = await store.aget(THREAD_TOMBSTONES_NS, f"{owner}:{thread_id}")
        if tombstone is not None:
            continue
        existing = await store.aget(THREADS_NS, thread_id)
        if existing is not None:
            continue

        ckpt_meta = getattr(checkpoint_tuple, "metadata", {}) or {}
        metadata = {k: v for k, v in ckpt_meta.items() if k not in ("created_at", "updated_at", "step", "source", "writes", "parents")}
        metadata["user_id"] = owner
        checkpoint_data = getattr(checkpoint_tuple, "checkpoint", {}) or {}
        channel_values = checkpoint_data.get("channel_values", {}) or {}
        values: dict[str, Any] = {}
        title = channel_values.get("title")
        if title:
            values["title"] = title
        created_at = ckpt_meta.get("created_at", time.time())
        updated_at = ckpt_meta.get("updated_at", created_at)
        await store.aput(
            THREADS_NS,
            thread_id,
            {
                "thread_id": thread_id,
                "status": _derive_thread_status_from_checkpoint_tuple(checkpoint_tuple),
                "created_at": created_at,
                "updated_at": updated_at,
                "metadata": metadata,
                "values": values,
            },
        )
        backfilled += 1
    return backfilled


async def start_run(
    body: Any,
    thread_id: str,
    request: Request,
    current_user: CurrentUser | None = None,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task.

    Parameters
    ----------
    body : RunCreateRequest
        The validated request body (typed as Any to avoid circular import
        with the router module that defines the Pydantic model).
    thread_id : str
        Target thread.
    request : Request
        FastAPI request — used to retrieve singletons from ``app.state``.
    """
    enforce_run_user_identity(body, current_user)

    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    body_context = getattr(body, "context", None) or {}
    model_name = body_context.get("model_name")

    # Coerce non-string model_name values to str before truncation.
    if model_name is not None and not isinstance(model_name, str):
        model_name = str(model_name)

    # Validate model against the allowlist when a model_name is provided.
    if model_name:
        app_config = get_app_config()
        resolved = app_config.get_model_config(model_name)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Model {model_name!r} is not in the configured model allowlist",
            )

    try:
        record = await run_mgr.create_or_reject(
            thread_id,
            body.assistant_id,
            on_disconnect=disconnect,
            metadata=body.metadata or {},
            kwargs={"input": body.input, "config": body.config},
            multitask_strategy=body.multitask_strategy,
            model_name=model_name,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedStrategyError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    # Ensure the thread is visible in SQL thread metadata store first.
    store = get_store(request)
    md = dict(body.metadata or {})
    user_id = getattr(current_user, "id", None)
    if user_id is not None:
        md["user_id"] = str(user_id)
    try:
        await _upsert_thread_in_thread_store(request, thread_id, md, body.assistant_id)
    except Exception:
        logger.warning("Failed to upsert thread %s in thread metadata store (non-fatal)", thread_id, exc_info=True)

    # Keep old store path as compatibility mirror only.
    if store is not None:
        await _upsert_thread_in_store(store, thread_id, md)

    agent_factory = resolve_agent_factory(body.assistant_id)
    graph_input = normalize_input(body.input)
    config = build_run_config(thread_id, body.config, body.metadata, assistant_id=body.assistant_id)

    # Merge DeerFlow-specific context overrides into both ``configurable`` and ``context``.
    # The ``context`` field is a custom extension for the langgraph-compat layer
    # that carries agent configuration (model_name, thinking_enabled, etc.).
    # Only agent-relevant keys are forwarded; unknown keys (e.g. thread_id) are ignored.
    merge_run_context_overrides(config, getattr(body, "context", None))
    inject_authenticated_user_context(config, request)

    # Canonical thread owner for checkpoints (Casdoor JWT `sub` ≠ local user UUID).
    auth_uid = getattr(current_user, "id", None)
    if auth_uid is not None:
        config.setdefault("configurable", {})["user_id"] = str(auth_uid)

    stream_modes = normalize_stream_modes(body.stream_mode)

    task = asyncio.create_task(
        run_agent(
            bridge,
            run_mgr,
            record,
            ctx=get_run_context(request),
            agent_factory=agent_factory,
            graph_input=graph_input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
            interrupt_before=body.interrupt_before,
            interrupt_after=body.interrupt_after,
        )
    )
    record.task = task

    # After the run completes, sync the title generated by TitleMiddleware from
    # the checkpointer into the Store record so that /threads/search returns the
    # correct title instead of an empty values dict.
    if store is not None:
        asyncio.create_task(_sync_thread_title_after_run(task, thread_id, checkpointer, store))

    return record


async def sse_consumer(
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_mgr: RunManager,
):
    """Async generator that yields SSE frames from the bridge.

    The ``finally`` block implements ``on_disconnect`` semantics:
    - ``cancel``: abort the background task on client disconnect.
    - ``continue``: let the task run; events are discarded.
    """
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        async for entry in bridge.subscribe(record.run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                break

            if entry is HEARTBEAT_SENTINEL:
                yield ": heartbeat\n\n"
                continue

            if entry is END_SENTINEL:
                end_payload = _build_end_event_payload(record)
                record.metadata["finished_at"] = end_payload["finished_at"]
                record.metadata["finished_at_ms"] = end_payload["finished_at_ms"]
                record.metadata["duration_ms"] = end_payload["duration_ms"]
                if "started_at" in end_payload:
                    record.metadata["started_at"] = end_payload["started_at"]
                yield format_sse("end", end_payload, event_id=entry.id or None)
                return

            yield format_sse(entry.event, entry.data, event_id=entry.id or None)

    finally:
        if record.status in (RunStatus.pending, RunStatus.running):
            if record.on_disconnect == DisconnectMode.cancel:
                await run_mgr.cancel(record.run_id)

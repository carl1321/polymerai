# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Detect LangGraph interrupt used for workflow async detach."""

from __future__ import annotations

from typing import Any


def is_workflow_interrupt(exc: BaseException) -> bool:
    """True when *exc* is a LangGraph pause (detach / resume), not a real failure."""
    try:
        from langgraph.errors import GraphInterrupt
    except ImportError:
        GraphInterrupt = ()  # type: ignore[misc, assignment]

    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, GraphInterrupt):
            return True
        name = type(cur).__name__
        if name in ("GraphInterrupt", "NodeInterrupt"):
            return True
        if "Interrupt(" in str(cur) and "async_task_id" in str(cur):
            return True
        cur = cur.__cause__ or cur.__context__

    return False


def is_interrupt_error_message(error: str) -> bool:
    """Detect interrupt payloads wrongly stored as node/run errors."""
    text = error or ""
    return "Interrupt(" in text and "async_task_id" in text


def has_interrupt_in_invoke_result(result: Any) -> bool:
    """LangGraph may return __interrupt__ in invoke result instead of raising."""
    if result is None:
        return False
    if isinstance(result, dict) and result.get("__interrupt__"):
        return True
    return False


def workflow_interrupt_detail(exc: BaseException) -> Any | None:
    """Extract interrupt payload from GraphInterrupt.args when present."""
    args = getattr(exc, "args", None)
    if not args:
        return None
    first = args[0]
    if isinstance(first, tuple) and first:
        item = first[0]
        return getattr(item, "value", item)
    return getattr(first, "value", first)

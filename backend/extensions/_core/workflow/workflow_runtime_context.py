# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Per-run workflow execution context (not stored in LangGraph checkpoints)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

_workflow_state_manager: ContextVar[Optional[Any]] = ContextVar(
    "workflow_state_manager",
    default=None,
)


def set_workflow_state_manager(state_manager: Any | None) -> None:
    _workflow_state_manager.set(state_manager)


def get_workflow_state_manager() -> Optional[Any]:
    return _workflow_state_manager.get()

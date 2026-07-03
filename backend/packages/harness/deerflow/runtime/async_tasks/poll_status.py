"""Map sandbox poll stdout JSON to async_tasks.status (single place)."""

from __future__ import annotations

import json
from typing import Any


def extract_poll_json(stdout: str) -> dict[str, Any] | None:
    lines = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
    for line in reversed(lines):
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def map_poll_dict_to_task_status(d: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Returns (async_tasks.status, error dict or None)."""
    phase = d.get("status") or d.get("phase")
    if phase is None:
        return "running", None
    if not isinstance(phase, str):
        return "running", None
    p = phase.lower()
    if p in ("submitted", "running", "pending"):
        return "running", None
    if p in ("completed", "succeeded", "success"):
        return "succeeded", None
    if p == "failed":
        err = d.get("error")
        if isinstance(err, dict):
            return "failed", err
        return "failed", {"message": str(err) if err is not None else "failed"}
    if p == "cancelled":
        return "cancelled", None
    if p == "timeout":
        return "timeout", None
    return "running", None


_TRANSIENT_POLL_ERROR_MARKERS = (
    "connection reset",
    "connection aborted",
    "connection refused",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "network is unreachable",
    "broken pipe",
    "econnreset",
)


def is_transient_poll_error(err: dict[str, Any] | None) -> bool:
    if not err:
        return False
    msg = str(err.get("message") or err.get("detail") or err).lower()
    return any(marker in msg for marker in _TRANSIENT_POLL_ERROR_MARKERS)


def extract_poll_result(d: dict[str, Any]) -> dict[str, Any] | None:
    r = d.get("result")
    if isinstance(r, dict):
        return r
    if r is not None:
        return {"value": r}
    return None

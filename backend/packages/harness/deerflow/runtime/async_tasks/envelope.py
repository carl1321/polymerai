"""Submit-tool stdout envelope: last-line JSON with status=submitted."""

from __future__ import annotations

import json
import re
from typing import Any


def tool_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif "text" in block and isinstance(block["text"], str):
                    parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


_JSON_LINE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


def _iter_json_candidates(text: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    candidates: list[dict[str, Any]] = []
    # Prefer last line that looks like JSON object
    for line in reversed(lines):
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
            break
    if candidates:
        return candidates
    # Fallback: scan for {...} substrings from bottom
    for m in reversed(list(_JSON_LINE.finditer(text))):
        try:
            obj = json.loads(m.group())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
            break
    return candidates


def resolve_submit_envelope(raw_tool_output: str) -> dict[str, Any] | None:
    """Return structured submit envelope if *raw_tool_output* contains a valid submitted JSON line."""
    for obj in _iter_json_candidates(raw_tool_output):
        if obj.get("status") != "submitted":
            continue
        if obj.get("defer") is False:
            return None
        if not obj.get("task_kind"):
            continue
        return obj
    return None


def redact_poll_command_from_submitted_envelope_text(text: str) -> str:
    """Remove ``poll_command`` from the last submitted-envelope JSON line (model-visible tool output)."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        raw = lines[i].strip()
        if not raw.startswith("{"):
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("status") != "submitted" or "poll_command" not in obj:
            continue
        redacted = dict(obj)
        redacted.pop("poll_command", None)
        lines[i] = json.dumps(redacted, ensure_ascii=False)
        return "\n".join(lines)
    return text

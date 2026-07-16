"""Canonical serialization for LangChain / LangGraph objects.

Provides a single source of truth for converting LangChain message
objects, Pydantic models, and LangGraph state dicts into plain
JSON-serialisable Python structures.

Consumers: ``deerflow.runtime.runs.worker`` (SSE publishing) and
``app.gateway.routers.threads`` (REST responses).
"""

from __future__ import annotations

import re
from typing import Any

_OUTPUTS_PREFIX = "/mnt/user-data/outputs/"
_RELATIVE_IMAGE_NAME_RE = re.compile(r"^[^/\s][^/\n]*\.(?:png|jpg|jpeg|webp|svg|gif|bmp)$", re.IGNORECASE)
_MARKDOWN_IMAGE_RE = re.compile(
    r"(!\[[^\]]*\]\()([^)]+)(\))",
    re.IGNORECASE,
)
_HTML_IMG_SRC_RE = re.compile(
    r"(<img\b[^>]*\bsrc\s*=\s*)([\"']?)([^\"'\s>]+)(\2)",
    re.IGNORECASE,
)

try:
    from langgraph.checkpoint.serde.jsonplus import _msgpack_ext_hook_to_json
except Exception:  # pragma: no cover
    _msgpack_ext_hook_to_json = None


def _normalize_image_path(path: str) -> str:
    candidate = path.strip()
    lowered = candidate.lower()
    if candidate.startswith("/") or "://" in candidate or lowered.startswith("data:") or lowered.startswith("blob:") or lowered.startswith("#"):
        return path
    if _RELATIVE_IMAGE_NAME_RE.match(candidate):
        return f"{_OUTPUTS_PREFIX}{candidate}"
    return path


def _normalize_output_image_paths_in_text(text: str) -> str:
    def _replace_markdown(match: re.Match[str]) -> str:
        prefix, raw_path, suffix = match.groups()
        normalized = _normalize_image_path(raw_path)
        return f"{prefix}{normalized}{suffix}"

    def _replace_html(match: re.Match[str]) -> str:
        before, quote, raw_path, _ = match.groups()
        normalized = _normalize_image_path(raw_path)
        if quote:
            return f"{before}{quote}{normalized}{quote}"
        return f"{before}{normalized}"

    normalized = _MARKDOWN_IMAGE_RE.sub(_replace_markdown, text)
    normalized = _HTML_IMG_SRC_RE.sub(_replace_html, normalized)
    return normalized


def _decode_legacy_msgpack_ext(value: Any) -> Any:
    """Decode legacy `[ext_code, hex_payload]` structures from migrated checkpoints."""
    if _msgpack_ext_hook_to_json is None:
        return value
    if isinstance(value, list):
        if len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
            payload = value[1].strip()
            if payload and len(payload) % 2 == 0:
                try:
                    decoded = _msgpack_ext_hook_to_json(value[0], bytes.fromhex(payload))
                    if decoded is not None:
                        return decoded
                except Exception:
                    pass
        return [_decode_legacy_msgpack_ext(item) for item in value]
    if isinstance(value, dict):
        return {k: _decode_legacy_msgpack_ext(v) for k, v in value.items()}
    return value


def serialize_lc_object(obj: Any) -> Any:
    """Recursively serialize a LangChain object to a JSON-serialisable dict."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return _normalize_output_image_paths_in_text(obj)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: serialize_lc_object(_decode_legacy_msgpack_ext(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_lc_object(_decode_legacy_msgpack_ext(item)) for item in obj]
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    # Pydantic v1 / older objects
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    # Last resort
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def serialize_channel_values(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values, stripping internal LangGraph keys.

    Internal keys like ``__pregel_*`` and ``__interrupt__`` are removed
    to match what the LangGraph Platform API returns.
    """
    result: dict[str, Any] = {}
    for key, value in channel_values.items():
        if key.startswith("__pregel_") or key == "__interrupt__":
            continue
        result[key] = serialize_lc_object(value)
    return result


def serialize_messages_tuple(obj: Any) -> Any:
    """Serialize a messages-mode tuple ``(chunk, metadata)``."""
    if isinstance(obj, tuple) and len(obj) == 2:
        chunk, metadata = obj
        return [serialize_lc_object(chunk), metadata if isinstance(metadata, dict) else {}]
    return serialize_lc_object(obj)


def serialize(obj: Any, *, mode: str = "") -> Any:
    """Serialize LangChain objects with mode-specific handling.

    * ``messages`` — obj is ``(message_chunk, metadata_dict)``
    * ``values`` — obj is the full state dict; ``__pregel_*`` keys stripped
    * everything else — recursive ``model_dump()`` / ``dict()`` fallback
    """
    if mode == "messages":
        return serialize_messages_tuple(obj)
    if mode == "values":
        return serialize_channel_values(obj) if isinstance(obj, dict) else serialize_lc_object(obj)
    return serialize_lc_object(obj)

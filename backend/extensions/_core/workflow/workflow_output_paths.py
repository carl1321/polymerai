# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Resolve workflow node output file references relative to run work_root."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_file_ref(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("file"), str) and bool(value["file"].strip())


def resolve_file_value(work_root: str | None, value: Any) -> Any:
    """If value is {\"file\": \"rel\"}, return absolute path string when work_root is set."""
    if not is_file_ref(value) or not work_root:
        return value
    raw = str(value["file"]).strip()
    if not raw:
        return value
    p = Path(raw).expanduser()
    if p.is_absolute():
        return str(p.resolve())
    return str((Path(work_root) / raw.lstrip("/")).resolve())


def to_relative_file_ref(work_root: str | None, path: Any) -> dict[str, str] | Any:
    """Normalize a path string to {\"file\": \"relative\"} under work_root."""
    if path is None or path == "":
        return {"file": ""}
    if is_file_ref(path):
        return path
    if not work_root:
        return {"file": str(path)}
    p = Path(str(path))
    root = Path(work_root).resolve()
    try:
        rel = p.resolve().relative_to(root)
        return {"file": rel.as_posix()}
    except ValueError:
        return {"file": str(path)}


_META_KEYS = frozenset({"source"})


def resolve_start_input_value(
    workflow_inputs: dict[str, Any],
    user_payload: dict[str, Any],
) -> Any:
    """Canonical value for {{开始.input}} / {{start.input}} templates."""
    raw = workflow_inputs.get("input")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    preferred_keys = ("poscar_path", "poscar", "structure", "contcar", "cif_path")
    for key in preferred_keys:
        if key in user_payload:
            return user_payload[key]
    for key, val in user_payload.items():
        if key in _META_KEYS:
            continue
        if is_file_ref(val):
            return val
    for key, val in user_payload.items():
        if key in _META_KEYS:
            continue
        if isinstance(val, (str, int, float, bool)) and val != "":
            return val
    if len(user_payload) == 1:
        return next(iter(user_payload.values()))
    return user_payload if user_payload else ""


def path_under_work_root(work_root: str | None, path: str) -> str:
    """Absolute host path → relative path under work_root (for LLM prompts / logs)."""
    if not work_root or not path:
        return path
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        return str(path).strip().lstrip("/")
    try:
        return p.resolve().relative_to(Path(work_root).resolve()).as_posix()
    except ValueError:
        return str(p)


def format_file_ref_for_template(
    value: Any,
    work_root: str | None,
    *,
    file_path_style: str = "absolute",
) -> str | None:
    """Render a file ref for templates: absolute (tools) or relative (LLM display)."""
    if is_file_ref(value):
        rel = str(value["file"]).strip().lstrip("/")
        if file_path_style == "relative":
            return rel
        if work_root:
            return str(resolve_file_value(work_root, value))
        return rel
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if file_path_style == "relative" and work_root:
            return path_under_work_root(work_root, text)
        p = Path(text).expanduser()
        if p.is_file():
            if file_path_style == "relative" and work_root:
                return path_under_work_root(work_root, str(p.resolve()))
            return str(p.resolve())
    return None


_STRUCTURE_KEYS = ("poscar_path", "poscar", "structure", "contcar", "result", "POTCAR", "POSCAR")


def structure_path_from_node_output(
    node_output: dict[str, Any] | None,
    work_root: str | None,
    *,
    relative: bool = False,
) -> str | None:
    if not isinstance(node_output, dict):
        return None
    for key in ("result", "output", "input"):
        block = node_output.get(key)
        if isinstance(block, dict):
            if relative:
                for val in block.values():
                    if is_file_ref(val):
                        return str(val["file"]).strip().lstrip("/")
            for val in block.values():
                if is_file_ref(val):
                    abs_p = resolve_file_value(work_root, val) if work_root else val.get("file")
                    if isinstance(abs_p, str) and Path(abs_p).is_file():
                        if relative and work_root:
                            return path_under_work_root(work_root, abs_p)
                        return abs_p
            for field in _STRUCTURE_KEYS:
                if field in block:
                    found = structure_path_from_block(block.get(field), work_root, relative=relative)
                    if found:
                        return found
        else:
            found = structure_path_from_block(block, work_root, relative=relative)
            if found:
                return found
    return None


def structure_path_from_block(value: Any, work_root: str | None, *, relative: bool = False) -> str | None:
    if value is None:
        return None
    if is_file_ref(value):
        if relative:
            return str(value["file"]).strip().lstrip("/")
        if work_root:
            abs_p = resolve_file_value(work_root, value)
            if isinstance(abs_p, str) and Path(abs_p).is_file():
                return abs_p
        return None
    if isinstance(value, str) and value.strip():
        text = value.strip().strip('"').strip("'")
        p = Path(text).expanduser()
        if not p.is_absolute() and work_root:
            p = (Path(work_root) / text.lstrip("/")).resolve()
        elif not p.is_absolute():
            return None
        else:
            p = p.resolve()
        if p.is_file():
            if relative and work_root:
                return path_under_work_root(work_root, str(p))
            return str(p)
    return None


def file_ref_exists(work_root: str | None, value: Any) -> bool:
    if not is_file_ref(value) or not work_root:
        return True
    raw = str(value["file"]).strip()
    if not raw:
        return False
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.is_file()
    return (Path(work_root) / raw.lstrip("/")).is_file()

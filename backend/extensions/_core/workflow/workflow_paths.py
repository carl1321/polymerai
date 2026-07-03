# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Thread ↔ workflow run file bridge (seed_files, copy-back)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)


def resolve_thread_uri(uri: str, *, user_id: str, thread_id: str) -> Path:
    """Resolve ``thread://uploads/foo`` or ``thread://workspace/bar`` to host path."""
    parsed = urlparse(uri)
    if parsed.scheme != "thread":
        raise ValueError(f"Unsupported seed URI scheme: {uri!r}")
    paths = get_paths()
    rel = (parsed.path or "").lstrip("/")
    if not rel:
        raise ValueError(f"Empty thread URI path: {uri!r}")
    if rel.startswith("uploads/"):
        base = paths.sandbox_uploads_dir(thread_id, user_id=user_id)
        return (base / rel[len("uploads/") :]).resolve()
    if rel.startswith("workspace/"):
        base = paths.sandbox_work_dir(thread_id, user_id=user_id)
        return (base / rel[len("workspace/") :]).resolve()
    if rel.startswith("outputs/"):
        base = paths.sandbox_outputs_dir(thread_id, user_id=user_id)
        return (base / rel[len("outputs/") :]).resolve()
    raise ValueError(f"thread:// URI must start with uploads/, workspace/, or outputs/: {uri!r}")


def apply_seed_files(
    *,
    user_id: str,
    run_id: str,
    thread_id: str | None,
    seed_files: list[dict[str, Any]] | None,
) -> None:
    if not seed_files or not thread_id:
        return
    paths = get_paths()
    inputs_dir = paths.workflow_run_inputs_dir(user_id, run_id)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    for item in seed_files:
        if not isinstance(item, dict):
            continue
        src_uri = str(item.get("from") or "")
        dest_rel = str(item.get("to") or "").lstrip("/")
        if not src_uri or not dest_rel:
            continue
        src = resolve_thread_uri(src_uri, user_id=user_id, thread_id=thread_id)
        if not src.is_file():
            logger.warning("seed_files: missing source %s -> %s", src_uri, src)
            continue
        dest = (inputs_dir / dest_rel).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def copy_run_outputs_to_thread(
    *,
    user_id: str,
    run_id: str,
    thread_id: str,
) -> Path:
    """Copy workflow run outputs/ to thread outputs/from-workflow-{run_id}/."""
    paths = get_paths()
    src = paths.workflow_run_outputs_dir(user_id, run_id)
    dest = paths.sandbox_outputs_dir(thread_id, user_id=user_id) / f"from-workflow-{run_id}"
    dest.mkdir(parents=True, exist_ok=True)
    if src.exists():
        for child in src.iterdir():
            target = dest / child.name
            if child.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)
    return dest

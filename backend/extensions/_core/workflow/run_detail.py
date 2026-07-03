# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Build workflow run detail payloads for the runs detail API."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def resolve_configured_node_name(node_id: str, data: Any) -> str:
    """节点名称：与编辑器「节点名称」(taskName) 一致，不用 node_id / displayName 作为主名。"""
    if not isinstance(data, dict):
        return str(node_id)
    for key in ("taskName", "nodeName", "node_name"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    label = data.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return str(node_id)


def build_node_index_from_spec(spec: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map node id -> { node_name, display_name, type, skill }."""
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(spec, dict):
        return index
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return index
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid:
            continue
        nid_str = str(nid)
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        node_name = resolve_configured_node_name(nid_str, data)
        display_name = data.get("displayName") or data.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = data.get("label")
        skill = data.get("llmSkill") or data.get("llm_skill")
        index[nid_str] = {
            "node_name": node_name,
            "display_name": str(display_name).strip() if display_name else node_name,
            "type": str(node.get("type") or ""),
            "skill": str(skill).strip() if skill else None,
        }
    return index


def _duration_ms(started_at: Any, finished_at: Any) -> int | None:
    if not started_at or not finished_at:
        return None
    try:
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if isinstance(finished_at, str):
            finished_at = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        if isinstance(started_at, datetime) and isinstance(finished_at, datetime):
            return int((finished_at - started_at).total_seconds() * 1000)
    except (TypeError, ValueError):
        pass
    return None


def _effective_node_input(task_input: Any, task_output: Any) -> Any:
    if task_input is not None and task_input != {} and task_input != "":
        return task_input
    if isinstance(task_output, dict):
        resolved = task_output.get("resolved_inputs")
        if resolved is not None:
            return resolved
    return task_input


def enrich_node_tasks(
    tasks: list[dict[str, Any]],
    node_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for task in tasks:
        nid = str(task.get("node_id") or "")
        meta = node_index.get(nid) or {}
        node_name = meta.get("node_name") or nid
        output = task.get("output")
        enriched.append(
            {
                "id": task.get("id"),
                "node_id": nid,
                "node_name": node_name,
                "display_name": meta.get("display_name"),
                "node_type": meta.get("type") or "",
                "skill": meta.get("skill"),
                "status": task.get("status"),
                "started_at": task.get("started_at"),
                "finished_at": task.get("finished_at"),
                "duration_ms": _duration_ms(task.get("started_at"), task.get("finished_at")),
                "input": _effective_node_input(task.get("input"), output),
                "output": output,
                "error": task.get("error"),
                "metrics": task.get("metrics"),
                "run_seq": task.get("run_seq"),
            }
        )
    enriched.sort(key=lambda x: (x.get("run_seq") is None, x.get("run_seq") or 0))
    return enriched


def enrich_async_tasks(
    rows: list[dict[str, Any]],
    node_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        nid = str(row.get("workflow_node_id") or "")
        meta = node_index.get(nid) or {}
        task_name = row.get("display_name") or row.get("task_kind") or "async_task"
        out.append(
            {
                "id": row.get("id"),
                "task_name": str(task_name),
                "job_id": row.get("external_ref"),
                "status": row.get("status"),
                "started_at": row.get("created_at"),
                "finished_at": row.get("finished_at"),
                "next_poll_at": row.get("next_poll_at"),
                "error": row.get("error"),
                "workflow_node_id": nid or None,
                "node_name": meta.get("node_name") if nid else None,
                "task_kind": row.get("task_kind"),
            }
        )
    return out


def build_run_detail_payload(
    run: dict[str, Any],
    release_spec: dict[str, Any] | None,
    tasks: list[dict[str, Any]],
    async_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    node_index = build_node_index_from_spec(release_spec)
    return {
        "run": run,
        "release_spec": release_spec,
        "node_index": node_index,
        "nodes": enrich_node_tasks(tasks, node_index),
        "async_tasks": enrich_async_tasks(async_tasks, node_index),
    }

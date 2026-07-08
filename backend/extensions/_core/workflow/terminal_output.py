# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""终态输出解析：采集工作流各节点输出并解析产出文件为统一结构。

阶段一目标：采集 + 解析（文件清单/元信息），不读取文件内容、不拷贝。
解析结果供 output_parser 节点保存到 node_tasks.output / run_logs / workflow_runs.output，
为后续对接外部数据库入库做准备。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from extensions._core.workflow.workflow_output_paths import (
    is_file_ref,
    resolve_file_value,
)

SCHEMA_VERSION = 1

# 节点输出中优先作为“执行结果主体”的键
_PRIMARY_KEYS = ("output", "result")


def extract_primary_result(node_output: Any) -> Any:
    """从单个节点的完整输出字典中取“执行结果主体”。

    优先 output，其次 result，都没有则返回整体。
    """
    if isinstance(node_output, dict):
        for key in _PRIMARY_KEYS:
            if key in node_output:
                return node_output[key]
    return node_output


def _file_manifest_item(field: str, work_root: str | None, ref: dict[str, Any]) -> dict[str, Any]:
    """把单个文件引用 {"file": rel} 解析为清单项（不读内容）。"""
    rel = str(ref.get("file", "")).strip()
    resolved = resolve_file_value(work_root, ref)
    abs_path = resolved if isinstance(resolved, str) else None
    exists = bool(abs_path and os.path.isfile(abs_path))
    size = os.path.getsize(abs_path) if exists else None
    filename = os.path.basename(rel or (abs_path or ""))
    ext = os.path.splitext(filename)[1]
    return {
        "field": field,
        "filename": filename,
        "relative_path": rel or None,
        "absolute_path": abs_path,
        "exists": exists,
        "size": size,
        "ext": ext,
    }


def _walk_for_files(value: Any, field: str, work_root: str | None, out: list[dict[str, Any]]) -> None:
    """递归遍历节点输出，收集所有文件引用。

    命中文件引用后不再深入其内部；dict/list 继续递归并记录 dotted 字段路径。
    """
    if is_file_ref(value):
        out.append(_file_manifest_item(field, work_root, value))
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            child_field = f"{field}.{key}" if field else str(key)
            _walk_for_files(sub, child_field, work_root, out)
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            child_field = f"{field}[{idx}]"
            _walk_for_files(sub, child_field, work_root, out)


def extract_file_manifest(node_output: Any, work_root: str | None) -> list[dict[str, Any]]:
    """解析单个节点输出中的全部产出文件为清单（不读内容、不拷贝）。"""
    manifest: list[dict[str, Any]] = []
    _walk_for_files(node_output, "", work_root, manifest)
    return manifest


def build_terminal_output(
    saved_node_ids: list[str],
    node_outputs: dict[str, Any],
    node_meta: dict[str, dict[str, Any]],
    work_root: str | None,
) -> dict[str, Any]:
    """把被选中节点的输出组装成统一终态结构。

    Args:
        saved_node_ids: 要保存的节点 id 列表（已按选择逻辑过滤）。
        node_outputs: 图状态里的全量节点输出（node_id -> 完整输出字典）。
        node_meta: 节点元信息（node_id -> {node_name, node_type, skill}）。
        work_root: run 的工作根目录，用于解析文件相对路径。

    Returns:
        {"__terminal__": {schema_version, generated_at, saved_node_ids, nodes[], file_count}}
    """
    nodes: list[dict[str, Any]] = []
    file_count = 0
    for nid in saved_node_ids:
        raw_output = node_outputs.get(nid, {})
        meta = node_meta.get(nid) or {}
        files = extract_file_manifest(raw_output, work_root)
        file_count += len(files)
        nodes.append(
            {
                "node_id": nid,
                "node_name": meta.get("node_name") or nid,
                "node_type": meta.get("node_type") or "",
                "skill": meta.get("skill"),
                "result": extract_primary_result(raw_output),
                "raw_output": raw_output,
                "files": files,
            }
        )
    return {
        "__terminal__": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(),
            "saved_node_ids": list(saved_node_ids),
            "nodes": nodes,
            "file_count": file_count,
        }
    }


def select_saved_node_ids(
    node_outputs: dict[str, Any],
    self_node_id: str,
    save_all: bool | None,
    save_node_ids: list[str] | None,
) -> list[str]:
    """决定要保存哪些节点。

    - save_all 为 true，或未显式指定 save_node_ids 时：保存全部已执行节点（排除自身）。
    - 否则：保存 save_node_ids 中确实存在输出的节点（排除自身），保持给定顺序。
    """
    if save_all or not save_node_ids:
        return [nid for nid in node_outputs.keys() if nid != self_node_id]
    return [nid for nid in save_node_ids if nid != self_node_id and nid in node_outputs]

# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Deterministic projection of skill tool results into workflow node_outputs."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from extensions._core.workflow.compiler import format_node_output
from extensions._core.workflow.workflow_output_paths import (
    file_ref_exists,
    is_file_ref,
    to_relative_file_ref,
)

logger = logging.getLogger(__name__)

_FILE_FIELD_NAMES = frozenset(
    {"contcar", "poscar", "poscar_path", "chgcar", "work_dir", "workdir", "potcar", "outcar", "vasprun"}
)


def _try_parse_json_loose(text: str) -> Any | None:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        if inner:
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    try:
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return None


def _validate_llm_json_shape(
    parsed: Any,
    *,
    output_format: str,
    output_fields: list[dict[str, Any]],
) -> bool:
    if parsed is None:
        return False
    if output_format == "array":
        if not isinstance(parsed, list) or len(parsed) == 0:
            return False
        items = parsed
    else:
        if isinstance(parsed, list):
            if len(parsed) != 1 or not isinstance(parsed[0], dict):
                return False
            items = parsed
        elif isinstance(parsed, dict):
            items = [parsed]
        else:
            return False
    for item in items:
        if not isinstance(item, dict):
            return False
        for field in output_fields:
            if not isinstance(field, dict):
                continue
            name = field.get("name")
            if not name:
                continue
            if name not in item:
                return False
            val = item.get(name)
            if val is None:
                return False
            if field.get("type") == "File":
                if not is_file_ref(val) and not (
                    isinstance(val, dict) and str(val.get("file") or "").strip()
                ):
                    if val in (None, ""):
                        return False
                continue
            if val == "":
                return False
    return True


_SKILL_ARTIFACT_NAMES: dict[str, tuple[str, ...]] = {
    "POTCAR": ("POTCAR",),
    "potcar": ("POTCAR",),
    "relax_poscar": ("CONTCAR", "POSCAR"),
    "poscar_path": ("POSCAR", "result.POSCAR"),
    "poscar": ("POSCAR", "result.POSCAR"),
}


def _artifact_paths_for_field(
    field_name: str,
    *,
    node_work_dir: str | None,
) -> list[Path]:
    if not node_work_dir:
        return []
    wd = Path(node_work_dir)
    names = _SKILL_ARTIFACT_NAMES.get(field_name, (field_name,))
    out: list[Path] = []
    for name in names:
        out.append(wd / name)
        if "." not in name:
            out.append(wd / f"result.{name}")
    return out


def _build_schema_payload_from_exec(
    exec_body: dict[str, Any],
    output_fields: list[dict[str, Any]],
    *,
    work_root: str | None,
    node_work_dir: str | None,
) -> dict[str, Any] | None:
    """Build node output object from skill exec when LLM JSON is missing (align POTCAR build success)."""
    if not output_fields:
        return None
    payload: dict[str, Any] = {}
    any_file = False
    for field in output_fields:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        ftype = field.get("type", "String")
        if not name:
            continue
        val = exec_body.get(name)
        if ftype == "File":
            if _file_field_needs_exec_fill(val):
                for candidate in _artifact_paths_for_field(str(name), node_work_dir=node_work_dir):
                    if candidate.is_file():
                        val = to_relative_file_ref(work_root, str(candidate.resolve()))
                        break
            if is_file_ref(val) and work_root:
                val = to_relative_file_ref(work_root, str(val["file"]))
            if not is_file_ref(val) or not file_ref_exists(work_root, val):
                continue
            payload[str(name)] = val
            any_file = True
        elif val is not None and val != "":
            payload[str(name)] = val
    if not any_file and not payload:
        return None
    payload.setdefault("success", bool(exec_body.get("success", True)))
    return payload


def _file_field_needs_exec_fill(val: Any) -> bool:
    if val is None or val == "":
        return True
    if is_file_ref(val):
        return False
    if isinstance(val, dict) and "file" in val:
        return not str(val.get("file") or "").strip()
    return True


def _merge_one_object(
    llm_obj: dict[str, Any],
    exec_body: dict[str, Any],
    output_fields: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    out = dict(llm_obj)
    for field in output_fields or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        ftype = field.get("type", "String")
        if not name:
            continue
        exec_val = exec_body.get(name)
        llm_val = out.get(name)
        if ftype == "File":
            if exec_val and _file_field_needs_exec_fill(llm_val):
                out[name] = exec_val
        elif (llm_val is None or llm_val == "") and exec_val is not None:
            out[name] = exec_val
    if "success" in exec_body:
        out["success"] = exec_body["success"]
    return out


def _merge_llm_with_exec(
    llm_out: Any,
    exec_body: dict[str, Any],
    *,
    output_format: str,
    output_fields: list[dict[str, Any]] | None,
) -> Any:
    if output_format == "array":
        items = llm_out if isinstance(llm_out, list) else [llm_out]
        return [_merge_one_object(item if isinstance(item, dict) else {}, exec_body, output_fields) for item in items]
    if isinstance(llm_out, list) and len(llm_out) == 1 and isinstance(llm_out[0], dict):
        return _merge_one_object(llm_out[0], exec_body, output_fields)
    if isinstance(llm_out, dict):
        return _merge_one_object(llm_out, exec_body, output_fields)
    return _merge_one_object({}, exec_body, output_fields)


def _normalize_output_files(
    body: dict[str, Any],
    *,
    work_root: str | None,
    output_fields: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    file_keys: set[str] = set(_FILE_FIELD_NAMES)
    if output_fields:
        for f in output_fields:
            if isinstance(f, dict) and f.get("type") == "File" and f.get("name"):
                file_keys.add(str(f["name"]))
    out = dict(body)
    missing = False
    for key in file_keys:
        if key not in out:
            continue
        val = out[key]
        if val is None or val == "":
            missing = True
            continue
        if not is_file_ref(val):
            out[key] = to_relative_file_ref(work_root, val)
        elif work_root:
            out[key] = to_relative_file_ref(work_root, str(val["file"]))
        if work_root and not file_ref_exists(work_root, out[key]):
            missing = True
    if missing:
        out["success"] = False
    return out


def _read_summary_json(work_dir: str | None) -> dict[str, Any] | None:
    if not work_dir:
        return None
    path = Path(work_dir) / "summary.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("Failed to read summary.json at %s", path, exc_info=True)
        return None


def _coerce_tool_payload(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return None


def _fill_files_from_node_work_dir(
    body: dict[str, Any],
    *,
    work_root: str | None,
    node_work_dir: str | None,
    output_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not node_work_dir:
        return body
    wd = Path(node_work_dir)
    out = dict(body)
    if output_fields:
        file_keys: set[str] = set()
        for f in output_fields:
            if isinstance(f, dict) and f.get("type") == "File" and f.get("name"):
                file_keys.add(str(f["name"]))
    else:
        file_keys = set(_FILE_FIELD_NAMES)
    for key in file_keys:
        candidate = wd / key
        if candidate.is_file() and (not out.get(key) or out.get(key) == ""):
            out[key] = to_relative_file_ref(work_root, str(candidate.resolve()))
    if not out.get("work_dir"):
        out["work_dir"] = str(wd.resolve())
    return out


def _extract_detach_envelope(tool_results: list[Any]) -> dict[str, Any] | None:
    from extensions._core.workflow.workflow_async_tasks import capture_envelope_from_tool_output

    for raw in tool_results:
        if isinstance(raw, dict):
            nested = raw.get("async_envelope")
            if isinstance(nested, dict) and nested.get("status") == "submitted" and nested.get("task_kind"):
                return nested
            text = json.dumps(raw, ensure_ascii=False, default=str)
        else:
            text = raw if isinstance(raw, str) else str(raw)
        env = capture_envelope_from_tool_output(text)
        if env:
            return env
    return None


def _build_exec_body(
    tool_results: list[Any],
    *,
    work_dir_hint: str | None,
    node_work_dir: str | None,
    output_fields: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for raw in tool_results:
        payload = _coerce_tool_payload(raw)
        if payload:
            merged.update(payload)
    summary_dir = node_work_dir or merged.get("work_dir") or work_dir_hint
    summary = _read_summary_json(str(summary_dir) if summary_dir else None)
    if summary:
        merged = {**merged, **summary}
    success = bool(merged.get("success", True))
    if "exit_code" in merged:
        success = int(merged.get("exit_code") or 0) == 0
    body = _fill_files_from_node_work_dir(
        {**merged, "success": success},
        work_root=work_dir_hint,
        node_work_dir=node_work_dir or merged.get("work_dir"),
        output_fields=output_fields,
    )
    return _normalize_output_files(
        body,
        work_root=work_dir_hint,
        output_fields=output_fields,
    )


def format_skill_output(
    *,
    tool_results: list[Any],
    output_format: str = "json",
    output_fields: list[dict[str, Any]] | None = None,
    work_dir_hint: str | None = None,
    node_work_dir: str | None = None,
    llm_response: str | None = None,
) -> dict[str, Any]:
    """Merge run_skill results with the LLM's strict JSON final answer (when output_fields configured)."""
    exec_body = _build_exec_body(
        tool_results,
        work_dir_hint=work_dir_hint,
        node_work_dir=node_work_dir,
        output_fields=output_fields,
    )

    detach_env = _extract_detach_envelope(tool_results)
    if detach_env:
        out = format_node_output(
            {
                "success": False,
                "status": "submitted",
                "work_dir": exec_body.get("work_dir") or work_dir_hint,
                "external_ref": detach_env.get("external_ref") or exec_body.get("external_ref"),
                "task_kind": detach_env.get("task_kind") or exec_body.get("task_kind"),
            },
            output_format,
            output_fields,
        )
        out.setdefault("output", {})
        if isinstance(out["output"], dict):
            out["output"]["_awaiting_external"] = True
        return out

    has_schema = bool(
        output_fields and isinstance(output_fields, list) and len(output_fields) > 0
    )

    if has_schema:
        parsed_llm = _try_parse_json_loose(llm_response or "")
        if not _validate_llm_json_shape(
            parsed_llm, output_format=output_format, output_fields=output_fields
        ):
            fallback = _build_schema_payload_from_exec(
                exec_body,
                output_fields,
                work_root=work_dir_hint,
                node_work_dir=node_work_dir,
            )
            if fallback and _validate_llm_json_shape(
                fallback, output_format=output_format, output_fields=output_fields
            ):
                return format_node_output(fallback, output_format, output_fields)
            err_msg = (
                "LLM final response must be valid JSON strictly matching "
                "the node output schema (all required fields present)"
            )
            wrapped = format_node_output(
                {"errors": err_msg, "success": False},
                output_format,
                output_fields,
            )
            payload = wrapped.get("output")
            if isinstance(payload, dict):
                payload["success"] = False
                payload["errors"] = err_msg
            return wrapped
        llm_raw = parsed_llm
        if output_format != "array" and isinstance(parsed_llm, list) and len(parsed_llm) == 1:
            llm_raw = parsed_llm[0]
        merged_payload = _merge_llm_with_exec(
            llm_raw,
            exec_body,
            output_format=output_format,
            output_fields=output_fields,
        )
        if output_format == "array":
            if isinstance(merged_payload, list):
                normalized_items = [
                    _normalize_output_files(
                        item if isinstance(item, dict) else {},
                        work_root=work_dir_hint,
                        output_fields=output_fields,
                    )
                    for item in merged_payload
                ]
            else:
                normalized_items = []
            return format_node_output(normalized_items, output_format, output_fields)

        merged_dict = merged_payload if isinstance(merged_payload, dict) else {}
        merged_dict = _normalize_output_files(
            merged_dict,
            work_root=work_dir_hint,
            output_fields=output_fields,
        )
        if not merged_dict.get("success", True):
            merged_dict["success"] = False
        return format_node_output(merged_dict, output_format, output_fields)

    if tool_results or exec_body:
        if not exec_body and tool_results:
            return format_node_output(
                {
                    "success": False,
                    "errors": "No parseable skill output",
                    "raw": tool_results[-1] if tool_results else None,
                },
                output_format,
                output_fields,
            )
        return format_node_output(exec_body, output_format, output_fields)

    return format_node_output(
        {"success": False, "errors": "No parseable skill output", "raw": None},
        output_format,
        output_fields,
    )

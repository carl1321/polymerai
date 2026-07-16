from __future__ import annotations

import hashlib
import logging
from typing import Any

from langchain_core.tools import BaseTool

from deerflow.tools import get_available_tools
from extensions._core.workflow_tools import db as wf_db
from extensions._core.workflow_tools.schema_utils import cached_schema_to_parameters, tool_args_schema_to_parameters
from extensions._core.workflow_tools.workflow_tool_loader import build_script_tool

logger = logging.getLogger(__name__)

_script_cache: dict[str, tuple[str, BaseTool]] = {}


def _script_cache_key(name: str, script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return f"{name}:{digest}"


def invalidate_script_tool(name: str) -> None:
    keys = [k for k in _script_cache if k.startswith(f"{name}:")]
    for k in keys:
        _script_cache.pop(k, None)


def get_script_tool(row: dict[str, Any]) -> BaseTool:
    name = row["name"]
    script = row.get("script") or ""
    key = _script_cache_key(name, script)
    cached = _script_cache.get(key)
    if cached is not None:
        return cached[1]
    tool = build_script_tool(script, name)
    _script_cache[key] = (key, tool)
    return tool


def get_workflow_tool_by_name(tool_name: str) -> BaseTool | None:
    from extensions._core.app_db import get_app_db_connection

    try:
        conn = get_app_db_connection()
        try:
            row = wf_db.get_tool_by_name(conn, tool_name)
            if row and row.get("source") == "script" and row.get("status") == "published":
                return get_script_tool(row)

            tools = get_available_tools(include_mcp=True, subagent_enabled=False)
            by_name = {t.name: t for t in tools}
            builtin = by_name.get(tool_name)
            if builtin is None:
                return None

            row = wf_db.get_tool_by_name(conn, tool_name)
            if row and row.get("source") in ("builtin", "mcp"):
                if not row.get("enabled"):
                    return None
                if row.get("status") != "published":
                    return None
            elif row is None:
                return None
            return builtin
        except Exception as db_error:
            if _is_missing_workflow_tools_table(db_error):
                tools = get_available_tools(include_mcp=True, subagent_enabled=False)
                return next((t for t in tools if t.name == tool_name), None)
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.warning("get_workflow_tool_by_name fallback for %s: %s", tool_name, e)
        tools = get_available_tools(include_mcp=True, subagent_enabled=False)
        return next((t for t in tools if t.name == tool_name), None)


def _row_to_tool_definition(row: dict[str, Any], parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "description": row.get("description") or row.get("display_name") or "",
        "parameters": parameters,
        "source": row.get("source"),
        "displayName": row.get("display_name"),
    }


def _fallback_tool_definitions(include_mcp: bool) -> list[dict[str, Any]]:
    """When catalog DB is unavailable, expose all runtime tools (legacy behavior)."""
    tools = get_available_tools(include_mcp=include_mcp, subagent_enabled=False)
    return [
        {
            "name": t.name,
            "description": getattr(t, "description", None) or "",
            "parameters": tool_args_schema_to_parameters(t),
            "source": "builtin",
            "displayName": t.name,
        }
        for t in tools
    ]


def _is_missing_workflow_tools_table(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "workflow_tools" in text and ("does not exist" in text or "undefinedtable" in text or "relation" in text)


def list_workflow_tool_definitions(include_mcp: bool = True) -> list[dict[str, Any]]:
    from extensions._core.app_db import get_app_db_connection

    conn = get_app_db_connection()
    try:
        try:
            rows = wf_db.list_tools(conn, catalog_only=True)
        except Exception as db_error:
            if _is_missing_workflow_tools_table(db_error):
                logger.warning("workflow_tools table missing; falling back to runtime tools: %s", db_error)
                return _fallback_tool_definitions(include_mcp)
            raise

        definitions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            name = row["name"]
            if name in seen:
                continue
            seen.add(name)
            if row.get("source") == "script":
                params = cached_schema_to_parameters(row.get("cached_schema"))
                if not params and row.get("script"):
                    try:
                        tool = get_script_tool(row)
                        params = tool_args_schema_to_parameters(tool)
                    except Exception as e:
                        logger.warning("Failed loading script tool %s schema: %s", name, e)
                        continue
                definitions.append(_row_to_tool_definition(row, params))
            else:
                tools = get_available_tools(include_mcp=include_mcp, subagent_enabled=False)
                match = next((t for t in tools if t.name == name), None)
                if match is None:
                    continue
                definitions.append(_row_to_tool_definition(row, tool_args_schema_to_parameters(match)))
        if not definitions:
            return _fallback_tool_definitions(include_mcp)
        return definitions
    except Exception as e:
        logger.exception("list_workflow_tool_definitions failed: %s", e)
        return _fallback_tool_definitions(include_mcp)
    finally:
        conn.close()

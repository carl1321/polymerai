"""Toolbox API: tool run history, tool list, and tool execution."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from deerflow.config import get_app_config
from extensions.auth.dependencies import CurrentUser, get_current_user
from extensions.toolbox import db as toolbox_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["toolbox"])


# ---------- Tool list (for toolbox UI) ----------


@router.get("/tools")
async def api_list_tools(_user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    """List available tools from config (name, group). For toolbox catalog UI."""
    config = get_app_config()
    items = [{"name": t.name, "group": t.group} for t in config.tools]
    return {"tools": items}


# ---------- Tool run history (align with agentic_workflow) ----------


@router.post("/tool-history")
async def api_save_tool_run(
    body: dict[str, Any],
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Save one tool run. Body: { tool_id, params?, result }."""
    tool_id = body.get("tool_id")
    params = body.get("params") or {}
    result = body.get("result")
    if not tool_id or result is None:
        raise HTTPException(status_code=400, detail="tool_id and result are required")
    result_str = result if isinstance(result, str) else str(result)
    try:
        rec = toolbox_db.save_tool_run(tool_id, params, result_str)
        return rec
    except Exception as e:
        logger.exception("Error saving tool run: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tool-history")
async def api_list_tool_runs(
    tool_id: str | None = Query(None, description="Filter by tool_id (optional)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List tool run records with optional tool_id filter."""
    try:
        records = toolbox_db.list_tool_runs(tool_id=tool_id, limit=limit, offset=offset)
        return {"records": records}
    except Exception as e:
        logger.exception("Error listing tool runs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tool-history/{record_id}")
async def api_get_tool_run(
    record_id: str,
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single tool run record."""
    rec = toolbox_db.get_tool_run(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


@router.delete("/tool-history/{record_id}")
async def api_delete_tool_run(
    record_id: str,
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a tool run record."""
    ok = toolbox_db.delete_tool_run(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True}


# ---------- Tool execution ----------


@router.post("/tools/execute")
async def api_execute_tool(
    body: dict[str, Any],
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute a tool by name with given arguments. Body: { tool_name, arguments }."""
    tool_name = body.get("tool_name")
    arguments = body.get("arguments") or {}
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")
    try:
        from deerflow.tools import get_available_tools

        tools = get_available_tools(include_mcp=True, subagent_enabled=False)
        by_name = {t.name: t for t in tools}
        tool = by_name.get(tool_name)
        if tool is None:
            available = sorted(by_name.keys())
            raise HTTPException(
                status_code=404,
                detail=f"Tool '{tool_name}' not found. Available: {available[:30]}{'...' if len(available) > 30 else ''}",
            )
        # Invoke: async or sync in executor
        if hasattr(tool, "ainvoke"):
            result = await tool.ainvoke(arguments)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: tool.invoke(arguments))
        result_str = str(result) if result is not None else ""
        # Optionally save to history
        try:
            toolbox_db.save_tool_run(tool_name, arguments, result_str)
        except Exception:
            pass
        return {"result": result_str}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error executing tool '%s': %s", tool_name, e)
        return {"result": "", "error": str(e)}

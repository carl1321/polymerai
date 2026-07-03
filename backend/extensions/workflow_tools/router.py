# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Global workflow tool catalog API (Coze-style configure → test → publish)."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from extensions.auth.dependencies import CurrentUser, get_current_user, require_admin
from extensions._core.app_db import get_app_db_connection
from extensions._core.db_errors import is_undefined_table
from extensions._core.workflow_tools import db as wf_db
from extensions._core.workflow_tools.registry import invalidate_script_tool, list_workflow_tool_definitions
from extensions._core.workflow_tools.schema_utils import tool_args_schema_to_parameters
from extensions._core.workflow_tools.workflow_tool_deps import (
    DepsInstallResult,
    ensure_script_imports,
    ensure_single_package,
    ensure_tool_requirements,
)
from extensions._core.workflow_tools.workflow_tool_loader import (
    load_tool_metadata,
    invoke_tool_script,
    metadata_to_cached_schema,
    parse_missing_module,
    parse_script_error_line,
)
from extensions._core.workflow_tools.workflow_tool_test_io import (
    clear_test_outputs,
    collect_output_artifacts,
    enrich_params_with_uploaded_paths,
    resolve_under_tool_test,
    save_uploaded_input,
    tool_test_inputs_dir,
    tool_test_outputs_dir,
)

logger = logging.getLogger(__name__)

# Mounted under workflows router (prefix /api) → /api/workflows/tool-catalog/*
router = APIRouter(prefix="/workflows/tool-catalog", tags=["workflow-tools"])

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class CreateToolRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str = ""


class UpdateToolRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    script: str | None = None
    requirements: str | None = None
    enabled: bool | None = None


class TestToolRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


def _test_failure_payload(error: str, logs: str = "", *, deps_error: bool = False, deps_message: str = "") -> dict[str, Any]:
    combined = logs or error
    line = parse_script_error_line(combined)
    payload: dict[str, Any] = {
        "success": False,
        "error": error,
        "logs": combined,
        "depsError": deps_error,
        "depsMessage": deps_message or error,
    }
    if line is not None:
        payload["errorLine"] = line
    return payload


def _validate_slug(name: str) -> None:
    if not _SLUG_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="name must be lowercase slug: start with letter, use letters/digits/underscore, 2-64 chars",
        )


def _output_files_payload(tool_id: str, files: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for f in files:
        rel = f.get("relativePath") or ""
        out.append(
            {
                "filename": f.get("filename") or Path(rel).name,
                "relativePath": rel,
                "downloadUrl": (
                    f"/api/workflows/tool-catalog/{tool_id}/test/download"
                    f"?relativePath={quote(rel, safe='')}"
                ),
            }
        )
    return out


async def _invoke_tool_test(row: dict[str, Any], tool_id: str, arguments: dict[str, Any]) -> Any:
    clear_test_outputs(tool_id)
    enriched = enrich_params_with_uploaded_paths(tool_id, arguments)
    return await asyncio.to_thread(
        invoke_tool_script,
        row["script"],
        row["name"],
        enriched,
        tool_id=tool_id,
    )


@router.get("")
async def list_workflow_tools_catalog(
    all_status: bool = Query(False, alias="all_status"),
    script_only: bool = Query(False, alias="script_only"),
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List tools for management UI or workflow catalog."""
    conn = get_app_db_connection()
    try:
        try:
            if all_status:
                rows = wf_db.list_tools(conn, source="script") if script_only else wf_db.list_tools(conn)
            else:
                rows = wf_db.list_tools(conn, catalog_only=True)
        except Exception as e:
            if is_undefined_table(e):
                logger.warning("workflow_tools table missing, returning empty list: %s", e)
                return {"tools": []}
            raise
        items = []
        for row in rows:
            params: list[dict[str, Any]] = []
            if row.get("source") == "script":
                from extensions._core.workflow_tools.schema_utils import cached_schema_to_parameters

                params = cached_schema_to_parameters(row.get("cached_schema"))
            items.append(
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "displayName": row.get("display_name"),
                    "description": row.get("description") or "",
                    "source": row.get("source"),
                    "sourceRef": row.get("source_ref"),
                    "status": row.get("status"),
                    "enabled": row.get("enabled"),
                    "lastTestOk": row.get("last_test_ok"),
                    "requirements": row.get("requirements") or "",
                    "parameters": params,
                }
            )
        return {"tools": items}
    finally:
        conn.close()


@router.get("/{tool_id}")
async def get_workflow_tool(
    tool_id: str,
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        from extensions._core.workflow_tools.schema_utils import cached_schema_to_parameters

        params = cached_schema_to_parameters(row.get("cached_schema"))
        return {
            "tool": {
                "id": str(row["id"]),
                "name": row["name"],
                "displayName": row.get("display_name"),
                "description": row.get("description") or "",
                "source": row.get("source"),
                "status": row.get("status"),
                "enabled": row.get("enabled"),
                "lastTestOk": row.get("last_test_ok"),
                "requirements": row.get("requirements") or "",
                "script": row.get("script") or "",
                "parameters": params,
            }
        }
    finally:
        conn.close()


@router.post("")
async def create_workflow_tool(
    body: CreateToolRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    _validate_slug(body.name)
    conn = get_app_db_connection()
    try:
        if wf_db.get_tool_by_name(conn, body.name):
            raise HTTPException(status_code=409, detail=f"Tool name '{body.name}' already exists")
        row = wf_db.create_script_tool(
            conn,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
        )
        return {"tool": row}
    finally:
        conn.close()


@router.delete("/{tool_id}")
async def delete_workflow_tool(
    tool_id: str,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        if row.get("source") != "script":
            raise HTTPException(status_code=400, detail="Only custom script tools can be deleted")
        name = row.get("name")
        if not wf_db.delete_tool(conn, tool_id):
            raise HTTPException(status_code=404, detail="Tool not found")
        if name:
            invalidate_script_tool(str(name))
        return {"ok": True, "id": tool_id}
    finally:
        conn.close()


@router.put("/{tool_id}")
async def update_workflow_tool(
    tool_id: str,
    body: UpdateToolRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        if row.get("source") != "script":
            fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in ("enabled", "display_name", "description")}
        else:
            fields = body.model_dump(exclude_unset=True)
        updated = wf_db.update_tool(conn, tool_id, fields)
        if updated and updated.get("source") == "script" and body.script is not None:
            invalidate_script_tool(updated["name"])
        return {"tool": updated}
    finally:
        conn.close()


@router.post("/{tool_id}/test")
async def test_workflow_tool(
    tool_id: str,
    body: TestToolRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row or row.get("source") != "script":
            raise HTTPException(status_code=404, detail="Script tool not found")

        deps: DepsInstallResult = ensure_script_imports(tool_id, row.get("script"))
        if not deps.ok:
            wf_db.update_tool(conn, tool_id, {"last_test_ok": False})
            return _test_failure_payload(
                deps.message,
                deps.detail or deps.message,
                deps_error=deps.deps_error,
                deps_message=deps.message,
            )

        logs = ""
        try:
            meta = load_tool_metadata(row["script"], row["name"], tool_id=tool_id)
            cached = metadata_to_cached_schema(meta)
            wf_db.update_tool(conn, tool_id, {"cached_schema": cached})
            result = await _invoke_tool_test(row, tool_id, body.params)
            output_files = _output_files_payload(tool_id, collect_output_artifacts(tool_id, result))
            wf_db.update_tool(conn, tool_id, {"last_test_ok": True, "cached_schema": cached})
            invalidate_script_tool(row["name"])
            return {
                "success": True,
                "output": result,
                "logs": logs,
                "parameters": cached.get("parameters", []),
                "outputFiles": output_files,
                "inputDir": str(tool_test_inputs_dir(tool_id)),
                "outputDir": str(tool_test_outputs_dir(tool_id)),
            }
        except Exception as e:
            err_text = str(e)
            logs = err_text
            missing = parse_missing_module(err_text)
            if missing:
                pkg_deps = ensure_single_package(missing)
                if not pkg_deps.ok:
                    wf_db.update_tool(conn, tool_id, {"last_test_ok": False})
                    return _test_failure_payload(
                        pkg_deps.message,
                        pkg_deps.detail or err_text,
                        deps_error=pkg_deps.deps_error,
                        deps_message=pkg_deps.message,
                    )
                try:
                    result = await _invoke_tool_test(row, tool_id, body.params)
                    meta = load_tool_metadata(row["script"], row["name"], tool_id=tool_id)
                    cached = metadata_to_cached_schema(meta)
                    output_files = _output_files_payload(tool_id, collect_output_artifacts(tool_id, result))
                    wf_db.update_tool(conn, tool_id, {"last_test_ok": True, "cached_schema": cached})
                    invalidate_script_tool(row["name"])
                    return {
                        "success": True,
                        "output": result,
                        "logs": f"Installed missing package: {missing}",
                        "parameters": cached.get("parameters", []),
                        "outputFiles": output_files,
                        "inputDir": str(tool_test_inputs_dir(tool_id)),
                        "outputDir": str(tool_test_outputs_dir(tool_id)),
                    }
                except Exception as retry_error:
                    err_text = str(retry_error)

            wf_db.update_tool(conn, tool_id, {"last_test_ok": False})
            return _test_failure_payload(err_text, logs or err_text)
    finally:
        conn.close()


@router.post("/{tool_id}/test/upload")
async def upload_workflow_tool_test_input(
    tool_id: str,
    file: UploadFile = File(...),
    field: str | None = Query(None),
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Upload a file into the tool test workspace inputs/ directory."""
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row or row.get("source") != "script":
            raise HTTPException(status_code=404, detail="Script tool not found")
        content = await file.read()
        info = save_uploaded_input(tool_id, file.filename or "file", content)
        return {"file": info, "field": field}
    finally:
        conn.close()


@router.get("/{tool_id}/test/download")
async def download_workflow_tool_test_file(
    tool_id: str,
    relativePath: str = Query(..., alias="relativePath"),
    _user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    """Download a file from tool test workspace (inputs/ or outputs/)."""
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
    finally:
        conn.close()
    path = resolve_under_tool_test(tool_id, relativePath)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=path, filename=path.name)


@router.post("/{tool_id}/publish")
async def publish_workflow_tool(
    tool_id: str,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        if row.get("source") == "script" and not row.get("last_test_ok"):
            raise HTTPException(status_code=400, detail="Run a successful test before publishing")
        updated = wf_db.update_tool(conn, tool_id, {"status": "published"})
        if updated and updated.get("source") == "script":
            invalidate_script_tool(updated["name"])
        return {"tool": updated}
    finally:
        conn.close()


@router.post("/import-system")
async def import_system_tools(
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    from deerflow.tools import get_available_tools

    conn = get_app_db_connection()
    count = 0
    try:
        tools = get_available_tools(include_mcp=True, subagent_enabled=False)
        for tool in tools:
            source = "mcp" if getattr(tool, "metadata", None) and tool.metadata.get("mcp_server") else "builtin"
            wf_db.upsert_system_tool(
                conn,
                name=tool.name,
                display_name=tool.name,
                description=(tool.description or "")[:2000],
                source=source,
                source_ref=tool.name,
            )
            count += 1
        return {"imported": count}
    finally:
        conn.close()


@router.patch("/{tool_id}/enabled")
async def set_tool_enabled(
    tool_id: str,
    body: dict[str, Any],
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="enabled is required")
    conn = get_app_db_connection()
    try:
        row = wf_db.get_tool_by_id(conn, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        updated = wf_db.update_tool(
            conn,
            tool_id,
            {"enabled": bool(enabled), "status": "published"},
        )
        return {"tool": updated}
    finally:
        conn.close()

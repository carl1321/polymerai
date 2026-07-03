"""Workflow API (DB-backed), ported from agentic_workflow."""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from extensions._core.app_db import get_app_db_connection
from extensions._core.db_errors import is_undefined_table
from extensions._core.workflow.run_detail import build_run_detail_payload
from extensions._core.workflow.runtime import db as wf_db
from extensions._core.workflow.runtime.executor import WorkflowExecutor
from extensions._core.workflow.workflow_request import (
    CreateReleaseRequest,
    CreateWorkflowRequest,
    SaveDraftRequest,
    UpdateWorkflowRequest,
)
from extensions.auth.dependencies import CurrentUser, get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["workflows"])

# Static paths under /workflows/* must register before /workflows/{workflow_id}
from extensions.workflow_tools.router import router as workflow_tool_catalog_router

router.include_router(workflow_tool_catalog_router)


class WorkflowExecuteRequest(BaseModel):
    workflowId: str
    inputs: dict[str, Any] | None = None
    files: list[str] | None = None
    threadId: str | None = None
    useDraft: bool = False
    draftId: str | None = None


def _iso(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in row.items()}


def _require_user(user: CurrentUser | None) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _check_workflow_permission(workflow: dict[str, Any], user: CurrentUser | None) -> None:
    """Minimal permission check (aligns with agentic_workflow default behavior)."""
    u = _require_user(user)
    if u.is_superuser:
        return
    created_by = workflow.get("created_by")
    if created_by and str(created_by) == str(u.id):
        return
    # Department/organization scopes (best-effort; depends on seeded data)
    lvl = getattr(u, "data_permission_level", "self")
    if lvl == "department" and u.department_id and workflow.get("department_id") == u.department_id:
        return
    if lvl == "organization" and u.organization_id and workflow.get("organization_id") == u.organization_id:
        return
    raise HTTPException(status_code=403, detail="You do not have permission to access this workflow")


# ---------------- Workflows CRUD ----------------


@router.get("/workflows")
async def list_workflows(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        created_by = None if user.is_superuser else str(user.id)
        try:
            workflows = wf_db.list_workflows(conn, status=status, created_by=created_by, limit=limit, offset=offset)
            with conn.cursor() as cur:
                parts = []
                params = []
                if status is not None:
                    parts.append("status = %s")
                    params.append(status)
                if created_by is not None:
                    parts.append("created_by = %s")
                    params.append(str(created_by))
                where_sql = " AND ".join(parts) if parts else "TRUE"
                cur.execute(
                    f"SELECT COUNT(*) AS total FROM workflows WHERE {where_sql}",
                    params,
                )
                total = cur.fetchone()["total"]
        except Exception as e:
            if is_undefined_table(e):
                logger.warning("workflows table missing, returning empty list: %s", e)
                return {"workflows": [], "total": 0, "limit": limit, "offset": offset}
            raise
        return {"workflows": [_row_to_dict(w) for w in workflows], "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.post("/workflows")
async def create_workflow(
    request: CreateWorkflowRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf_id = wf_db.create_workflow(
            conn,
            name=request.name,
            description=request.description,
            created_by=user.id,
            status=request.status,
            organization_id=user.organization_id,
            department_id=user.department_id,
        )
        conn.commit()
        wf = wf_db.get_workflow(conn, wf_id)
        if not wf:
            raise HTTPException(status_code=500, detail="Failed to retrieve created workflow")
        return _row_to_dict(wf)
    finally:
        conn.close()


# Static paths must register before /workflows/{workflow_id} (otherwise workflow_id="tools").
@router.get("/workflow/tools")
@router.get("/workflows/tools")
async def get_workflow_tools(
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Workflow editor tool list from global catalog (published script + enabled builtin/mcp)."""
    from extensions._core.workflow_tools.registry import list_workflow_tool_definitions

    try:
        definitions = list_workflow_tool_definitions(include_mcp=True)
    except Exception as e:
        logger.exception("Failed loading workflow catalog tools with MCP: %s", e)
        try:
            definitions = list_workflow_tool_definitions(include_mcp=False)
            logger.warning("Fallback to include_mcp=False for /api/workflows/tools")
        except Exception as fallback_error:
            logger.exception("Fallback loading workflow catalog failed: %s", fallback_error)
            try:
                from deerflow.tools import get_available_tools
                from extensions._core.workflow_tools.schema_utils import tool_args_schema_to_parameters

                tools = get_available_tools(include_mcp=False, subagent_enabled=False)
                definitions = [
                    {
                        "name": t.name,
                        "description": getattr(t, "description", None) or "",
                        "parameters": tool_args_schema_to_parameters(t),
                    }
                    for t in tools
                ]
            except Exception as legacy_error:
                logger.exception("Legacy tool list also failed: %s", legacy_error)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to load workflow tools: {fallback_error}",
                ) from fallback_error

    return [
        {
            "name": item["name"],
            "description": item.get("description") or "",
            "parameters": item.get("parameters") or [],
        }
        for item in definitions
    ]


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        return _row_to_dict(wf)
    finally:
        conn.close()


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    request: UpdateWorkflowRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        wf_db.update_workflow(conn, UUID(workflow_id), name=request.name, description=request.description, status=request.status)
        conn.commit()
        wf2 = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf2:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated workflow")
        return _row_to_dict(wf2)
    finally:
        conn.close()


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        ok = wf_db.delete_workflow(conn, UUID(workflow_id))
        conn.commit()
        return {"success": bool(ok)}
    finally:
        conn.close()


# ---------------- Drafts ----------------


@router.post("/workflows/{workflow_id}/draft")
async def save_draft(
    workflow_id: str,
    request: SaveDraftRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        draft_id = wf_db.save_draft(
            conn,
            workflow_id=UUID(workflow_id),
            graph=request.graph,
            created_by=user.id,
            is_autosave=request.is_autosave,
        )
        conn.commit()
        draft = wf_db.get_draft_by_id(conn, draft_id)
        return {"draft": _row_to_dict(draft) if draft else {"id": str(draft_id)}}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/draft")
async def get_draft(
    workflow_id: str,
    version: int | None = Query(None),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        draft = wf_db.get_draft(conn, UUID(workflow_id), version=version)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"draft": _row_to_dict(draft)}
    finally:
        conn.close()


# ---------------- Releases ----------------


@router.post("/workflows/{workflow_id}/release")
async def create_release(
    workflow_id: str,
    request: CreateReleaseRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        release_id = wf_db.create_release(
            conn,
            workflow_id=UUID(workflow_id),
            source_draft_id=UUID(request.source_draft_id),
            spec=request.spec,
            checksum=request.checksum,
            created_by=user.id,
        )
        conn.commit()
        rel = wf_db.get_release(conn, release_id)
        return {"release": _row_to_dict(rel) if rel else {"id": str(release_id)}}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/releases")
async def list_releases(
    workflow_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        rels = wf_db.list_releases(conn, UUID(workflow_id))
        return {"releases": [_row_to_dict(r) for r in rels]}
    finally:
        conn.close()


# ---------------- Runs ----------------


@router.get("/workflows/{workflow_id}/runs")
async def list_runs(
    workflow_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM workflow_runs
                WHERE workflow_id=%s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (UUID(workflow_id), limit, offset),
            )
            runs = [dict(r) for r in cur.fetchall()]
        return {"runs": [_row_to_dict(r) for r in runs], "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.post("/workflows/{workflow_id}/runs")
async def create_run(
    workflow_id: str,
    body: dict[str, Any],
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        release_id = wf.get("current_release_id")
        if not release_id:
            raise HTTPException(status_code=400, detail="Workflow has no current_release_id; publish a release first")
        inputs = body.get("inputs") or {}
        thread_id = body.get("thread_id") or body.get("threadId")
        source = body.get("source") or ("chat" if thread_id else "ui")
        executor = WorkflowExecutor()
        run_id = await executor.create_run(
            workflow_id=UUID(workflow_id),
            release_id=UUID(str(release_id)),
            inputs=inputs,
            created_by=user.id,
            thread_id=str(thread_id) if thread_id else None,
            source=str(source),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT input FROM workflow_runs WHERE id = %s", (run_id,))
            row = cur.fetchone()
        inp = row.get("input") if row else {}
        if isinstance(inp, str):
            inp = json.loads(inp)
        work_root = (inp or {}).get("work_root") if isinstance(inp, dict) else None
        return {"run_id": str(run_id), "status": "queued", "work_root": work_root}
    finally:
        conn.close()


@router.post("/workflows/{workflow_id}/runs/{run_id}/inputs")
async def upload_run_inputs(
    workflow_id: str,
    run_id: str,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Upload files into `{work_root}/inputs/` for a queued/running workflow run."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, input, created_by FROM workflow_runs WHERE id=%s AND workflow_id=%s",
                (UUID(run_id), UUID(workflow_id)),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        status = str(row.get("status") or "")
        if status not in ("queued", "running"):
            raise HTTPException(status_code=400, detail=f"Cannot upload to run in status {status}")
        inp = row.get("input") or {}
        if isinstance(inp, str):
            inp = json.loads(inp)
        work_root = (inp or {}).get("work_root")
        if not work_root:
            raise HTTPException(status_code=400, detail="Run has no work_root")
        from deerflow.config.paths import get_paths

        paths = get_paths()
        inputs_dir = paths.workflow_run_inputs_dir(str(row["created_by"]), run_id)
        inputs_dir.mkdir(parents=True, exist_ok=True)
        uploaded: list[dict[str, str]] = []
        for uf in files:
            safe_name = Path(uf.filename or "file").name
            dest = inputs_dir / safe_name
            content = await uf.read()
            dest.write_bytes(content)
            rel = f"inputs/{safe_name}"
            uploaded.append({"filename": safe_name, "path": str(dest), "relative": rel})
        return {"files": uploaded}
    finally:
        conn.close()


@router.patch("/workflows/{workflow_id}/runs/{run_id}/input")
async def patch_run_input(
    workflow_id: str,
    run_id: str,
    body: dict[str, Any],
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Merge keys into workflow_runs.input (e.g. poscar_path after upload)."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        patch = body.get("inputs") or body.get("input") or body
        if not isinstance(patch, dict):
            raise HTTPException(status_code=400, detail="Expected object body with inputs")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, input FROM workflow_runs WHERE id=%s AND workflow_id=%s",
                (UUID(run_id), UUID(workflow_id)),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        if str(row.get("status") or "") not in ("queued", "running"):
            raise HTTPException(status_code=400, detail="Run is not accepting input updates")
        inp = row.get("input") or {}
        if isinstance(inp, str):
            inp = json.loads(inp)
        merged = {**(inp if isinstance(inp, dict) else {}), **patch}
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workflow_runs SET input = %s WHERE id = %s",
                (json.dumps(merged), UUID(run_id)),
            )
            conn.commit()
        return {"input": merged, "work_root": merged.get("work_root")}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}/async-tasks")
async def get_run_async_tasks(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """List async_tasks rows linked to this workflow run (detach / long-running)."""
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, task_kind, display_name, external_ref, workflow_node_id,
                       poll_interval_seconds, next_poll_at, result, error, created_at, finished_at
                FROM async_tasks
                WHERE workflow_run_id = %s
                ORDER BY created_at DESC
                """,
                (UUID(run_id),),
            )
            rows = [dict(r) for r in cur.fetchall()]
        return {"async_tasks": [_row_to_dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}")
async def get_run(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workflow_runs WHERE id=%s AND workflow_id=%s", (UUID(run_id), UUID(workflow_id)))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"run": _row_to_dict(dict(row))}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}/tasks")
async def get_run_tasks(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        tasks = wf_db.get_run_tasks(conn, UUID(run_id))
        return {"tasks": [_row_to_dict(t) for t in tasks]}
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}/detail")
async def get_run_detail(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Aggregated run detail: nodes (with configured names), async tasks, release spec."""
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workflow_runs WHERE id=%s AND workflow_id=%s",
                (UUID(run_id), UUID(workflow_id)),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        run = _row_to_dict(dict(row))
        release_spec: dict[str, Any] | None = None
        release_id = run.get("release_id")
        if release_id:
            rel = wf_db.get_release(conn, UUID(str(release_id)))
            if rel and isinstance(rel.get("spec"), dict):
                release_spec = rel["spec"]
        tasks = [_row_to_dict(t) for t in wf_db.get_run_tasks(conn, UUID(run_id))]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, task_kind, display_name, external_ref, workflow_node_id,
                       created_at, finished_at, next_poll_at, error
                FROM async_tasks
                WHERE workflow_run_id = %s
                ORDER BY created_at ASC
                """,
                (UUID(run_id),),
            )
            async_rows = [_row_to_dict(dict(r)) for r in cur.fetchall()]
        return build_run_detail_payload(run, release_spec, tasks, async_rows)
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}/logs")
async def get_run_logs(
    workflow_id: str,
    run_id: str,
    node_id: str | None = Query(None),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, current_user)
        if node_id:
            logs = wf_db.get_node_logs(conn, UUID(run_id), node_id=node_id)
        else:
            logs = wf_db.get_run_logs(conn, UUID(run_id))
        return {"logs": [_row_to_dict(row) for row in logs]}
    finally:
        conn.close()


@router.post("/workflows/{workflow_id}/runs/{run_id}/cancel")
async def cancel_run(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        wf_db.update_run_status(conn, UUID(run_id), "canceled", finished_at=datetime.utcnow())
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


@router.post("/workflows/{workflow_id}/runs/{run_id}/retry")
async def retry_run(
    workflow_id: str,
    run_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        wf = wf_db.get_workflow(conn, UUID(workflow_id))
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        wf_db.update_run_status(conn, UUID(run_id), "queued", output=None, error=None, started_at=None, finished_at=None)
        conn.commit()
        return {"success": True, "status": "queued"}
    finally:
        conn.close()


# ---------------- agentic_workflow compatibility endpoints ----------------


async def _resolve_release_id_for_execute(
    conn,
    workflow_id: UUID,
    request: WorkflowExecuteRequest,
    created_by: UUID,
) -> UUID:
    wf = wf_db.get_workflow(conn, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if request.useDraft:
        draft = None
        if request.draftId:
            draft = wf_db.get_draft_by_id(conn, UUID(request.draftId))
            if not draft or draft.get("workflow_id") != workflow_id:
                raise HTTPException(status_code=404, detail="Draft not found")
        else:
            draft = wf_db.get_draft(conn, workflow_id)
        if not draft:
            raise HTTPException(status_code=400, detail="No draft found for this workflow")
        graph = draft.get("graph") or {}
        spec = wf_db._build_spec_from_graph(graph, wf.get("name") or "未命名工作流")
        checksum = hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return wf_db.create_release(
            conn,
            workflow_id=workflow_id,
            source_draft_id=UUID(str(draft["id"])),
            spec=spec,
            checksum=checksum,
            created_by=created_by,
            set_current=False,
        )

    release_id = wf.get("current_release_id")
    if not release_id:
        raise HTTPException(status_code=400, detail="Workflow has no current_release_id; publish a release first")
    return UUID(str(release_id))


@router.post("/workflow/execute")
@router.post("/workflows/execute")
async def execute_workflow_compat(
    request: WorkflowExecuteRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        workflow_id = UUID(request.workflowId)
        wf = wf_db.get_workflow(conn, workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        release_id = await _resolve_release_id_for_execute(conn, workflow_id, request, user.id)
        conn.commit()

        workflow_inputs = request.inputs or {}
        if request.files:
            workflow_inputs["files"] = request.files

        executor = WorkflowExecutor()
        run_id = await executor.create_run(
            workflow_id=workflow_id,
            release_id=release_id,
            inputs=workflow_inputs,
            created_by=user.id,
            thread_id=str(request.threadId) if request.threadId else None,
            source="chat" if request.threadId else "api",
        )
        return {"success": True, "result": {"run_id": str(run_id)}}
    finally:
        conn.close()


@router.post("/workflow/execute/stream")
@router.post("/workflows/execute/stream")
async def execute_workflow_stream_compat(
    request: WorkflowExecuteRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
):
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        workflow_id = UUID(request.workflowId)
        wf = wf_db.get_workflow(conn, workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        _check_workflow_permission(wf, user)
        release_id = await _resolve_release_id_for_execute(conn, workflow_id, request, user.id)
        conn.commit()

        workflow_inputs = request.inputs or {}
        if request.files:
            workflow_inputs["files"] = request.files

        executor = WorkflowExecutor()
        run_id = await executor.create_run(
            workflow_id=workflow_id,
            release_id=release_id,
            inputs=workflow_inputs,
            created_by=user.id,
        )

        async def event_generator():
            async for chunk in executor.execute_run_stream(run_id):
                yield chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    finally:
        conn.close()

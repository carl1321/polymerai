"""NewSAM execution history and utility APIs."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from extensions._core.app_db import get_app_db_connection
from extensions.auth.dependencies import CurrentUser, get_current_user_optional
from extensions.toolbox.agentic_tools.visualize_molecules_tool import smiles_to_3d_sdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/new-sam", tags=["new-sam"])
workflows_alias_router = APIRouter(prefix="/api/workflows/new-sam", tags=["new-sam"])


def _require_user(user: CurrentUser | None) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _iso(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in row.items()}


@router.post("/save-execution-history")
@workflows_alias_router.post("/save-execution-history")
async def save_execution_history(
    payload: dict[str, Any],
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    run_id = payload.get("runId")
    workflow_id = payload.get("workflowId")
    if not run_id or not workflow_id:
        raise HTTPException(status_code=400, detail="runId and workflowId are required")

    history_id = str(uuid4())
    name = (payload.get("name") or "").strip()
    if not name:
        name = f"运行记录 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO new_sam_execution_history (
                    id, run_id, workflow_id, user_id, name, objective, constraints, execution_state,
                    started_at, finished_at, execution_logs, node_outputs, iteration_node_outputs,
                    iteration_snapshots, workflow_graph, iteration_analytics, candidate_molecules
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s,
                    %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                )
                """,
                (
                    history_id,
                    run_id,
                    workflow_id,
                    str(user.id),
                    name,
                    json.dumps(payload.get("objective") or {}, ensure_ascii=False),
                    json.dumps(payload.get("constraints") or [], ensure_ascii=False),
                    payload.get("executionState") or "idle",
                    payload.get("startedAt"),
                    payload.get("finishedAt"),
                    json.dumps(payload.get("executionLogs") or [], ensure_ascii=False),
                    json.dumps(payload.get("nodeOutputs") or {}, ensure_ascii=False),
                    json.dumps(payload.get("iterationNodeOutputs") or {}, ensure_ascii=False),
                    json.dumps(payload.get("iterationSnapshots") or [], ensure_ascii=False),
                    json.dumps(payload.get("workflowGraph") or {}, ensure_ascii=False),
                    json.dumps(payload.get("iterationAnalytics") or {}, ensure_ascii=False),
                    json.dumps(payload.get("candidateMolecules") or [], ensure_ascii=False),
                ),
            )
        conn.commit()
        return {"success": True, "id": history_id}
    finally:
        conn.close()


@router.get("/execution-history")
@workflows_alias_router.get("/execution-history")
async def list_execution_history(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, workflow_id, name, execution_state, started_at, finished_at, created_at, candidate_molecules
                FROM new_sam_execution_history
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (str(user.id), limit, offset),
            )
            rows = [dict(r) for r in cur.fetchall()]

        history = []
        for r in rows:
            row = _normalize_row(r)
            candidate_molecules = row.get("candidate_molecules") or []
            molecule_count = len(candidate_molecules) if isinstance(candidate_molecules, list) else 0
            history.append(
                {
                    "id": row["id"],
                    "runId": row.get("run_id"),
                    "workflowId": row.get("workflow_id"),
                    "name": row.get("name"),
                    "executionState": row.get("execution_state"),
                    "startedAt": row.get("started_at"),
                    "finishedAt": row.get("finished_at"),
                    "createdAt": row.get("created_at"),
                    "moleculeCount": molecule_count,
                }
            )
        return {"success": True, "history": history}
    finally:
        conn.close()


@router.get("/execution-history/{history_id}")
@workflows_alias_router.get("/execution-history/{history_id}")
async def get_execution_history(
    history_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM new_sam_execution_history WHERE id = %s AND user_id = %s",
                (history_id, str(user.id)),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="History not found")
        r = _normalize_row(dict(row))
        history = {
            "id": r["id"],
            "runId": r.get("run_id"),
            "workflowId": r.get("workflow_id"),
            "name": r.get("name"),
            "objective": r.get("objective") or {},
            "constraints": r.get("constraints") or [],
            "executionState": r.get("execution_state"),
            "startedAt": r.get("started_at"),
            "finishedAt": r.get("finished_at"),
            "executionLogs": r.get("execution_logs") or [],
            "nodeOutputs": r.get("node_outputs") or {},
            "iterationNodeOutputs": r.get("iteration_node_outputs") or {},
            "iterationSnapshots": r.get("iteration_snapshots") or [],
            "workflowGraph": r.get("workflow_graph") or {},
            "iterationAnalytics": r.get("iteration_analytics") or {},
            "candidateMolecules": r.get("candidate_molecules") or [],
            "createdAt": r.get("created_at"),
            "updatedAt": r.get("updated_at"),
        }
        return {"success": True, "history": history}
    finally:
        conn.close()


@router.delete("/execution-history/{history_id}")
@workflows_alias_router.delete("/execution-history/{history_id}")
async def delete_execution_history(
    history_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM new_sam_execution_history WHERE id = %s AND user_id = %s",
                (history_id, str(user.id)),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        if not deleted:
            raise HTTPException(status_code=404, detail="History not found")
        return {"success": True}
    finally:
        conn.close()


@router.post("/generate-3d-sdf")
@workflows_alias_router.post("/generate-3d-sdf")
async def generate_3d_sdf(
    payload: dict[str, Any],
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    _require_user(current_user)
    smiles = str(payload.get("smiles") or "").strip()
    if not smiles:
        raise HTTPException(status_code=400, detail="smiles is required")
    sdf = smiles_to_3d_sdf(smiles)
    if not sdf:
        raise HTTPException(status_code=400, detail="3D SDF generation unavailable or invalid SMILES")
    return {"success": True, "sdf": sdf}

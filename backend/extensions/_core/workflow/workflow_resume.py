# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Resume workflow runs after async_tasks reach a terminal state."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from deerflow.persistence.async_task.model import AsyncTaskRow

from extensions._core.workflow.format_skill_output import format_skill_output
from extensions._core.workflow.runtime.db import get_db_connection, update_run_status
from extensions._core.workflow.runtime.executor import WorkflowExecutor
from extensions._core.workflow.workflow_paths import copy_run_outputs_to_thread

logger = logging.getLogger(__name__)


async def fail_workflow_after_async_task(row: AsyncTaskRow) -> bool:
    """Mark workflow/node failed when a linked async_task ends unsuccessfully."""
    if not row.workflow_run_id or not row.workflow_node_id:
        return False

    run_id = row.workflow_run_id
    node_id = row.workflow_node_id
    err_msg = "external async task failed"
    if isinstance(row.error, dict):
        err_msg = str(row.error.get("message") or row.error)
    elif row.error:
        err_msg = str(row.error)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE node_tasks
                SET status = 'failed',
                    error = %s,
                    finished_at = NOW()
                WHERE run_id = %s AND node_id = %s
                  AND status IN ('running', 'awaiting_external')
                """,
                (json.dumps({"error": err_msg}), run_id, node_id),
            )
        update_run_status(
            conn,
            run_id,
            "failed",
            error={
                "reason": "async_task_failed",
                "async_task_id": str(row.id),
                "node_id": node_id,
                "message": err_msg,
            },
            finished_at=datetime.now(),
        )
        conn.commit()
        logger.info(
            "Workflow run %s failed after async_task %s status=%s",
            run_id,
            row.id,
            row.status,
        )
        return True
    finally:
        conn.close()


async def resume_workflow_after_async_task(row: AsyncTaskRow) -> bool:
    """Queue workflow run for resume after external task completes."""
    if not row.workflow_run_id or not row.workflow_node_id:
        return False
    if row.status != "succeeded":
        return False

    run_id = row.workflow_run_id
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workflow_runs WHERE id = %s", (run_id,))
            run = cur.fetchone()
        if not run:
            return False

        output_fields = None
        output_format = "json"
        payload = row.payload if isinstance(row.payload, dict) else {}
        work_dir = payload.get("work_dir")
        if isinstance(row.result, dict) and row.result.get("work_dir"):
            work_dir = row.result.get("work_dir")

        tool_payload = row.result if isinstance(row.result, dict) else {"status": row.status, "result": row.result}
        if work_dir:
            tool_payload = {**tool_payload, "work_dir": work_dir}

        formatted = format_skill_output(
            tool_results=[json.dumps(tool_payload, ensure_ascii=False, default=str)],
            output_format=output_format,
            output_fields=output_fields,
            work_dir_hint=str(work_dir) if work_dir else None,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE node_tasks
                SET status = 'success', output = %s, finished_at = NOW()
                WHERE run_id = %s AND node_id = %s AND status IN ('running', 'awaiting_external')
                """,
                (json.dumps(formatted), run_id, row.workflow_node_id),
            )
            cur.execute(
                """
                UPDATE node_tasks SET async_task_id = %s
                WHERE run_id = %s AND node_id = %s
                """,
                (row.id, run_id, row.workflow_node_id),
            )

        inp = run.get("input") or {}
        if isinstance(inp, str):
            inp = json.loads(inp)
        inp = dict(inp or {})
        inp["_resume"] = {
            "node_id": row.workflow_node_id,
            "async_task_id": str(row.id),
            "node_output": formatted,
        }
        update_run_status(conn, run_id, "queued")
        with conn.cursor() as cur:
            cur.execute("UPDATE workflow_runs SET input = %s WHERE id = %s", (json.dumps(inp), run_id))
        conn.commit()

        thread_id = run.get("thread_id")
        created_by = str(run.get("created_by") or row.user_id)
        if thread_id and row.status == "succeeded":
            try:
                copy_run_outputs_to_thread(user_id=created_by, run_id=str(run_id), thread_id=str(thread_id))
            except Exception:
                logger.warning("copy_run_outputs_to_thread failed", exc_info=True)

        executor = WorkflowExecutor()
        try:
            from extensions._core.workflow.runtime.worker import get_workflow_worker

            get_workflow_worker().wake()
        except Exception:
            pass
        return True
    finally:
        conn.close()

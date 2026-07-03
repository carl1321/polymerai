"""Background tick: poll due async_tasks, webhook timeouts, terminal follow-up runs."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import subprocess
import sys
from typing import Any

from fastapi import FastAPI

from deerflow.config.paths import get_paths
from deerflow.persistence.async_task.model import AsyncTaskRow
from deerflow.runtime.async_tasks.poll_status import (
    extract_poll_json,
    extract_poll_result,
    is_transient_poll_error,
    map_poll_dict_to_task_status,
)
from deerflow.runtime.async_tasks.registry import get_async_task_handles
from deerflow.runtime.async_tasks.thread_bridge import sse_channel_for_thread
from deerflow.runtime.runs.schemas import DisconnectMode
from deerflow.sandbox.local.local_sandbox import LocalSandbox
from deerflow.sandbox.sandbox_provider import get_sandbox_provider
from deerflow.sandbox.tools import replace_virtual_paths_in_command

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timeout"})

# async_task poll_command runs via Sandbox.execute_command (same host shell as agent bash),
# not inside the uvicorn worker. A bare ``python`` picks PATH, not the Gateway venv — replace
# the first ``python``/``python3`` token with sys.executable so poll sees backend deps (pymatgen, …).
_POLL_CMD_PYTHON_TOKEN = re.compile(r"(?<![A-Za-z0-9/_.-])python3?(?=\s)")


def _poll_command_use_gateway_interpreter(cmd: str) -> str:
    if not (cmd and cmd.strip()):
        return cmd
    exe = shlex.quote(sys.executable)
    return _POLL_CMD_PYTHON_TOKEN.sub(exe, cmd, count=1)


def _thread_data_dict_for_async_poll(thread_id: str, user_id: str) -> dict[str, str]:
    """Paths for ``replace_virtual_paths_in_command`` (same layout as agent ``thread_data``)."""
    paths = get_paths()
    return {
        "workspace_path": str(paths.sandbox_work_dir(thread_id, user_id=user_id)),
        "uploads_path": str(paths.sandbox_uploads_dir(thread_id, user_id=user_id)),
        "outputs_path": str(paths.sandbox_outputs_dir(thread_id, user_id=user_id)),
        "shared_path": str(paths.sandbox_shared_dir()),
    }


def _poll_command_for_gateway_shell(cmd: str, *, row: AsyncTaskRow, sandbox: Any) -> str:
    """Prepare ``poll_command`` for ``Sandbox.execute_command``.

    ``LocalSandbox`` runs on the host and does not mount ``/mnt/user-data``; agent-facing
    virtual paths must be rewritten to the per-user thread directories. Container sandboxes
    (e.g. AioSandbox) keep virtual paths because ``/mnt/user-data`` is bind-mounted there.
    """
    cmd = _poll_command_use_gateway_interpreter(cmd)
    if isinstance(sandbox, LocalSandbox):
        td = _thread_data_dict_for_async_poll(row.thread_id, row.user_id)
        return replace_virtual_paths_in_command(cmd, td)
    return cmd


def _tick_seconds() -> float:
    return float(os.environ.get("DEER_FLOW_ASYNC_TASK_DISPATCH_TICK_SECONDS", "30"))


_POLL_LOG_CMD_CHARS = int(os.environ.get("DEER_FLOW_ASYNC_TASK_POLL_LOG_CMD_CHARS", "400"))
_POLL_LOG_STDOUT_CHARS = int(os.environ.get("DEER_FLOW_ASYNC_TASK_POLL_LOG_STDOUT_CHARS", "1200"))


def _preview_poll_command(cmd: str | None) -> str:
    if not cmd:
        return "<empty>"
    s = cmd.strip().replace("\n", " ")
    return f"{s[:_POLL_LOG_CMD_CHARS]}…" if len(s) > _POLL_LOG_CMD_CHARS else s


def _preview_poll_stdout(out: str | None) -> str:
    if out is None:
        return "<none>"
    stripped = out.strip()
    if not stripped:
        return "<empty>"
    one = stripped.replace("\r", "").replace("\n", " | ")
    return f"{one[:_POLL_LOG_STDOUT_CHARS]}…" if len(one) > _POLL_LOG_STDOUT_CHARS else one


_thread_locks: dict[str, asyncio.Lock] = {}


def _lock_for_thread(thread_id: str) -> asyncio.Lock:
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    return _thread_locks[thread_id]


def _outcome_for_sse(status: str) -> str | None:
    if status not in _TERMINAL:
        return None
    return status


async def _publish_update(
    bridge: Any,
    *,
    thread_id: str,
    row: AsyncTaskRow,
    previous_status: str,
) -> None:
    payload = {
        "type": "async_task_update",
        "task_id": str(row.id),
        "task_kind": row.task_kind,
        "status": row.status,
        "previous_status": previous_status,
        "external_ref": row.external_ref,
        "outcome": _outcome_for_sse(row.status),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error": row.error,
    }
    await bridge.publish(sse_channel_for_thread(thread_id), "custom", payload)


def _first_string_list_item(errors: Any) -> str | None:
    if not isinstance(errors, list) or not errors:
        return None
    e0 = errors[0]
    return e0.strip() if isinstance(e0, str) and e0.strip() else None


def _result_warning_excerpt(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    w = _first_string_list_item(result.get("errors"))
    if w:
        return w
    details = result.get("details")
    if isinstance(details, dict):
        return _first_string_list_item(details.get("errors"))
    return None


def _succeeded_followup_suffix(row: AsyncTaskRow) -> str:
    r = row.result
    if not isinstance(r, dict):
        return ""
    bits: list[str] = []
    warn = _result_warning_excerpt(r)
    if warn:
        bits.append(f"提醒：{warn}")
    if r.get("converged") is False:
        bits.append("未报告结构已完全收敛")
    fe = r.get("final_energy_eV")
    if fe is not None and str(fe).strip() != "":
        bits.append(f"报告末态能量：{fe} eV")
    if not bits:
        return ""
    return "（" + "；".join(bits) + "） "


def _followup_human_message(row: AsyncTaskRow) -> str:
    name = row.display_name or row.task_kind
    ref = row.external_ref or ""
    if row.status == "succeeded":
        extra = _succeeded_followup_suffix(row)
        return f"[系统通知] 后台异步任务「{name}」已完成（external_ref={ref}）。{extra}请根据已有上下文与任务结果，继续协助用户分析与下一步操作。"
    if row.status == "failed":
        err = row.error or {}
        summary = err.get("message") or err.get("code") or str(err)
        details = err.get("details")
        if isinstance(details, dict):
            w = _first_string_list_item(details.get("errors"))
            if isinstance(w, str) and w and w not in str(summary):
                summary = f"{summary}（{w}）"
        return f"[系统通知] 后台异步任务「{name}」失败：{summary}。请帮助用户理解原因并决定是否调整参数后重试。"
    if row.status == "cancelled":
        return f"[系统通知] 后台异步任务「{name}」已被取消（external_ref={ref}）。"
    if row.status == "timeout":
        return f"[系统通知] 后台异步任务「{name}」等待外部回调超时（external_ref={ref}）。"
    return f"[系统通知] 后台异步任务「{name}」已结束（status={row.status}）。"


async def _start_terminal_followup(app: FastAPI, row: AsyncTaskRow) -> None:
    handles = get_async_task_handles()
    if handles is None or handles.repo is None or handles.run_manager is None or handles.bridge is None or handles.run_context_factory is None:
        return

    from app.gateway.services import build_run_config, normalize_input, normalize_stream_modes, resolve_agent_factory

    ctx = handles.run_context_factory()
    text = _followup_human_message(row)
    outcome = row.status if row.status in _TERMINAL else "failed"
    md = {
        "user_id": row.user_id,
        "trigger": "async_task_terminal",
        "outcome": outcome,
        "async_task_id": str(row.id),
        "source_run_id": row.source_run_id,
    }
    graph_input = normalize_input({"messages": [{"role": "user", "content": text}]})
    config = build_run_config(row.thread_id, None, md, assistant_id="lead_agent")

    record = await handles.run_manager.create(
        thread_id=row.thread_id,
        assistant_id="lead_agent",
        on_disconnect=DisconnectMode.continue_,
        metadata=md,
        kwargs={"input": graph_input, "config": config},
    )

    ok = await handles.repo.mark_terminal_followup(row.id, resume_run_id=record.run_id)
    if not ok:
        await handles.run_manager.cancel(record.run_id)
        return

    from deerflow.runtime.runs.worker import run_agent

    agent_factory = resolve_agent_factory("lead_agent")
    task = asyncio.create_task(
        run_agent(
            handles.bridge,
            handles.run_manager,
            record,
            ctx=ctx,
            agent_factory=agent_factory,
            graph_input=graph_input,
            config=config,
            stream_modes=normalize_stream_modes(None),
            stream_subgraphs=False,
        )
    )
    record.task = task


def _workflow_host_poll_command(cmd: str) -> str:
    from deerflow.skills.loader import get_skills_root_path

    host_public = str(get_skills_root_path() / "public")
    out = _poll_command_use_gateway_interpreter(cmd)
    return out.replace("/mnt/skills/public", host_public)


async def _run_workflow_host_poll(repo: Any, row: AsyncTaskRow, *, prev_status: str, bridge: Any) -> None:
    """Execute poll_command on gateway host for workflow detach tasks (no thread sandbox)."""
    poll_cmd = _workflow_host_poll_command(row.poll_command or "")
    logger.info(
        "workflow async_task poll start run=%s task=%s ref=%s",
        row.workflow_run_id,
        row.id,
        row.external_ref,
    )
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["/bin/sh", "-c", poll_cmd],
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("DEER_FLOW_WORKFLOW_POLL_TIMEOUT_SECONDS", "600")),
        )
        out = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
    except Exception as exc:
        logger.warning(
            "workflow async_task poll failed run=%s task=%s: %s",
            row.workflow_run_id,
            row.id,
            exc,
            exc_info=True,
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return

    parsed = extract_poll_json(out)
    if not parsed:
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return

    new_status, err_part = map_poll_dict_to_task_status(parsed)
    if new_status == "failed" and is_transient_poll_error(err_part):
        logger.warning(
            "workflow async_task poll transient error run=%s task=%s: %s",
            row.workflow_run_id,
            row.id,
            err_part,
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return
    result = extract_poll_result(parsed)
    updated = await repo.apply_poll_success_update(
        row.id,
        previous_status=prev_status,
        new_status=new_status,
        payload_patch={"last_poll": parsed},
        result=result if new_status == "succeeded" else None,
        error=err_part if new_status == "failed" else None,
    )
    if updated:
        await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)


async def _run_one_poll(app: FastAPI, row: AsyncTaskRow) -> None:
    repo = getattr(app.state, "async_task_repo", None)
    handles = get_async_task_handles()
    if repo is None or handles is None or handles.bridge is None:
        return
    bridge = handles.bridge
    prev_status = row.status
    if row.workflow_run_id and row.poll_command:
        await _run_workflow_host_poll(repo, row, prev_status=prev_status, bridge=bridge)
        return
    provider = get_sandbox_provider()
    sb_id = provider.acquire(row.thread_id)
    sandbox = provider.get(sb_id)
    if sandbox is None:
        logger.warning(
            "async_task poll: sandbox unavailable thread=%s task=%s sb_id=%s (provider.get returned None)",
            row.thread_id,
            row.id,
            sb_id,
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return
    poll_cmd = _poll_command_for_gateway_shell(row.poll_command or "", row=row, sandbox=sandbox)
    try:
        out = sandbox.execute_command(poll_cmd)
    except Exception as exc:
        logger.warning(
            "async_task poll: poll_command failed thread=%s task=%s sb_id=%s cmd_preview=%s: %s",
            row.thread_id,
            row.id,
            sb_id,
            _preview_poll_command(poll_cmd),
            exc,
            exc_info=True,
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return

    parsed = extract_poll_json(out)
    if not parsed:
        logger.warning(
            "async_task poll: no parseable poll JSON thread=%s task=%s sb_id=%s chars=%s stdout_preview=%s",
            row.thread_id,
            row.id,
            sb_id,
            len(out or ""),
            _preview_poll_stdout(out),
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return

    new_status, err_part = map_poll_dict_to_task_status(parsed)
    if new_status == "failed" and is_transient_poll_error(err_part):
        logger.warning(
            "async_task poll transient error id=%s thread=%s: %s",
            row.id,
            row.thread_id,
            err_part,
        )
        updated = await repo.increment_poll_failure(row.id)
        if updated:
            await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)
        return
    result = extract_poll_result(parsed)
    patch = {"last_poll": parsed}
    updated = await repo.apply_poll_success_update(
        row.id,
        previous_status=prev_status,
        new_status=new_status,
        payload_patch=patch,
        result=result if new_status == "succeeded" else None,
        error=err_part if new_status == "failed" else None,
    )
    if updated:
        if updated.status != prev_status or updated.status in _TERMINAL:
            logger.info(
                "async_task poll: id=%s thread=%s kind=%s %s -> %s",
                row.id,
                row.thread_id,
                row.task_kind,
                prev_status,
                updated.status,
            )
        await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev_status)


async def async_task_dispatcher_loop(app: FastAPI, stop: asyncio.Event) -> None:
    repo = getattr(app.state, "async_task_repo", None)
    handles = get_async_task_handles()
    bridge = handles.bridge if handles else None
    if repo is None:
        logger.info("async_task dispatcher: no repo, exiting loop task")
        await stop.wait()
        return

    logger.info("async_task dispatcher started (tick=%ss)", _tick_seconds())

    while not stop.is_set():
        try:
            for row in await repo.list_webhook_wait_overdue(limit=32):
                prev = row.status
                updated = await repo.mark_webhook_timeout(row.id)
                if updated and bridge:
                    await _publish_update(bridge, thread_id=row.thread_id, row=updated, previous_status=prev)

            rows = await repo.iter_due_poll_tasks(limit=24)
            if rows:
                ids = ",".join(str(r.id) for r in rows[:12])
                if len(rows) > 12:
                    ids += ",..."
                logger.info(
                    "async_task dispatcher tick: %d due poll task(s) [%s]",
                    len(rows),
                    ids,
                )
            for row in rows:
                async with _lock_for_thread(row.thread_id):
                    await _run_one_poll(app, row)

            for row in await repo.list_terminal_unfollowed(limit=20):
                if row.workflow_run_id:
                    from extensions._core.workflow.workflow_resume import (
                        fail_workflow_after_async_task,
                        resume_workflow_after_async_task,
                    )

                    if row.status == "succeeded":
                        ok = await resume_workflow_after_async_task(row)
                    else:
                        ok = await fail_workflow_after_async_task(row)
                    if ok:
                        await repo.mark_terminal_followup(
                            row.id,
                            resume_run_id=str(row.workflow_run_id),
                        )
                else:
                    await _start_terminal_followup(app, row)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("async_task dispatcher tick failed")

        try:
            await asyncio.wait_for(stop.wait(), timeout=_tick_seconds())
        except TimeoutError:
            pass

    logger.info("async_task dispatcher stopped")


async def publish_async_task_manual(
    bridge: Any,
    *,
    thread_id: str,
    row: AsyncTaskRow,
    previous_status: str,
) -> None:
    await _publish_update(bridge, thread_id=thread_id, row=row, previous_status=previous_status)

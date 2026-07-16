# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""LangChain tool: run_skill for workflow LLM nodes."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from langchain_core.tools import tool
from pydantic import Field

from extensions._core.workflow.skill_runner import run_skill, skill_result_to_tool_json
from extensions._core.workflow.workflow_skill_paths import (
    build_skill_argv_from_refs,
    extract_file_refs_from_prompt,
    find_structure_path,
    resolve_workflow_work_dir,
    structure_path_from_refs,
)

logger = logging.getLogger(__name__)

# Set per-invocation by workflow compiler (workflow run context).
_workflow_tool_context: dict[str, Any] = {}


def set_workflow_tool_context(ctx: dict[str, Any] | None) -> None:
    global _workflow_tool_context
    _workflow_tool_context = dict(ctx or {})


def get_workflow_tool_context() -> dict[str, Any]:
    return dict(_workflow_tool_context)


def _enforce_allowed_skill(skill_name: str, ctx: dict[str, Any]) -> str | None:
    """Return error message if skill_name is outside the node-configured allowlist."""
    allowed = ctx.get("allowed_skill_name") or ctx.get("skill_name")
    if not allowed:
        return None
    if str(skill_name).strip() == str(allowed).strip():
        return None
    return (
        f"Skill {skill_name!r} is not allowed for this node; "
        f"use configured skill {allowed!r} only."
    )


def _run_skill_safe(
    skill_name: str,
    *,
    work_dir: str,
    argv: list[str] | None,
    kwargs: dict[str, Any] | None,
    command: str | None,
    require_detach: bool,
    timeout: int,
) -> dict[str, Any]:
    try:
        return run_skill(
            skill_name,
            work_dir=work_dir,
            argv=argv,
            kwargs=kwargs,
            command=command,
            exec_mode="shell" if command else None,
            sync_timeout=timeout,
            require_detach=require_detach,
        )
    except Exception as exc:
        logger.warning("run_skill failed for %r: %s", skill_name, exc, exc_info=True)
        return {
            "success": False,
            "detach_error": require_detach,
            "error_kind": "runner_exception",
            "error": str(exc),
            "exit_code": -1,
            "stderr": str(exc),
            "work_dir": work_dir,
        }


def _resolve_argv_and_cwd(
    skill_name: str,
    work_dir: str,
    argv: list[str] | None,
    command: str | None,
    ctx: dict[str, Any],
) -> tuple[str, list[str] | None]:
    cwd = resolve_workflow_work_dir(work_dir, ctx)
    resolved_argv = list(argv) if argv else None
    if not command and not resolved_argv:
        work_root = ctx.get("work_root")
        node_outputs = ctx.get("node_outputs")
        prompt = ctx.get("prompt")
        file_refs = extract_file_refs_from_prompt(
            prompt if isinstance(prompt, str) else None,
            node_outputs=node_outputs if isinstance(node_outputs, dict) else None,
            node_labels=ctx.get("node_labels"),
            work_root=str(work_root) if work_root else None,
        )
        ctx["file_refs"] = file_refs
        structure = structure_path_from_refs(file_refs) or find_structure_path(
            node_outputs=node_outputs,
            work_root=str(work_root) if work_root else None,
            prompt=prompt if isinstance(prompt, str) else None,
            ctx=ctx,
        )
        if structure:
            resolved_argv = build_skill_argv_from_refs(
                skill_name,
                structure,
                cwd,
                file_refs,
            )
    return str(cwd), resolved_argv


def invoke_workflow_skill(
    skill_name: str,
    *,
    work_dir: str = "",
    argv: list[str] | None = None,
    command: str | None = None,
) -> str:
    """Run skill on workflow worker (same resolution as run_skill_tool); for compiler fallback."""
    ctx = get_workflow_tool_context()
    blocked = _enforce_allowed_skill(skill_name, ctx)
    if blocked:
        return skill_result_to_tool_json(
            {
                "success": False,
                "error_kind": "skill_not_allowed",
                "error": blocked,
                "exit_code": -1,
                "stderr": blocked,
                "work_dir": work_dir,
            }
        )
    require_detach = bool(ctx.get("require_detach"))
    timeout = int(ctx.get("sync_timeout") or 3600)
    cwd, resolved_argv = _resolve_argv_and_cwd(skill_name, work_dir, argv, command, ctx)
    result = _run_skill_safe(
        skill_name,
        work_dir=cwd,
        argv=resolved_argv,
        kwargs=None,
        command=command,
        require_detach=require_detach,
        timeout=timeout,
    )
    return skill_result_to_tool_json(result)


@tool("run_skill")
def run_skill_tool(
    skill_name: Annotated[str, Field(description="Skill directory name, e.g. vasp-relax")],
    work_dir: Annotated[str, Field(description="Absolute host path for this step's working directory")],
    argv: Annotated[list[str] | None, Field(description="CLI argv passed to scripts/run.py")] = None,
    kwargs_json: Annotated[
        str | None,
        Field(description="Optional JSON object of keyword args (--key value) for run.py"),
    ] = None,
    command: Annotated[str | None, Field(description="Shell command for SKILL.md bash-only skills")] = None,
) -> str:
    """Execute a DeerFlow skill on the workflow worker (host paths, not sandbox /mnt/user-data)."""
    kw: dict[str, Any] | None = None
    if kwargs_json:
        parsed = json.loads(kwargs_json)
        if isinstance(parsed, dict):
            kw = parsed
    ctx = get_workflow_tool_context()
    blocked = _enforce_allowed_skill(skill_name, ctx)
    if blocked:
        return skill_result_to_tool_json(
            {
                "success": False,
                "error_kind": "skill_not_allowed",
                "error": blocked,
                "exit_code": -1,
                "stderr": blocked,
                "work_dir": work_dir,
            }
        )
    require_detach = bool(ctx.get("require_detach"))
    timeout = int(ctx.get("sync_timeout") or 3600)
    cwd, resolved_argv = _resolve_argv_and_cwd(skill_name, work_dir, argv, command, ctx)
    result = _run_skill_safe(
        skill_name,
        work_dir=cwd,
        argv=resolved_argv,
        kwargs=kw,
        command=command,
        require_detach=require_detach,
        timeout=timeout,
    )
    return skill_result_to_tool_json(result)

# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Lightweight tool-calling agent for workflow LLM nodes (no sandbox / MCP)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _read_skill_markdown(skill) -> str:
    """Load SKILL.md body from deerflow Skill (metadata only, no .content attr)."""
    try:
        path = getattr(skill, "skill_file", None)
        if path is None or not Path(path).is_file():
            return ""
        raw = Path(path).read_text(encoding="utf-8")
        return _FRONTMATTER_RE.sub("", raw, count=1).strip()
    except Exception:
        logger.debug("Failed to read SKILL.md for %s", getattr(skill, "name", "?"), exc_info=True)
        return ""


def _inject_skills_prompt(system_prompt: str | None, skill_names: list[str] | None) -> str:
    if not skill_names or len(skill_names) != 1:
        return system_prompt or ""
    from deerflow.skills.loader import load_skills

    skills = load_skills(enabled_only=False)
    by_name = {s.name: s for s in skills}
    name = skill_names[0]
    sk = by_name.get(name)
    blocks: list[str] = []
    if sk:
        body = _read_skill_markdown(sk)
        if body:
            blocks.append(f"## Skill: {name}\n\n{body}")
    if not blocks:
        logger.warning("Skill %s not found or SKILL.md empty; continuing without skill doc", name)
        return system_prompt or ""
    skills_text = "\n\n---\n\n".join(blocks)
    prefix = (
        "Workflow skill node rules:\n"
        "1. Call run_skill with host paths from the user message (never /mnt or sandbox paths).\n"
        "2. If run_skill returns success:false or detach_error:true, read stderr/exit_code, fix argv "
        "(--config, --executor, --potcar, work_dir, etc.), and call run_skill again before finishing.\n"
        "3. Only after run_skill returns async_envelope with status=submitted, reply with ONLY valid JSON "
        "strictly matching the output JSON Schema in this system message (no markdown fences, no extra text).\n"
        '4. Include every required field; File fields use {"file": "relative/path"} under workflow work_root.\n\n'
    )
    combined = prefix + skills_text
    if system_prompt:
        return system_prompt.strip() + "\n\n" + combined
    return combined


def _workflow_paths_user_block(workflow_context: dict[str, Any] | None) -> str:
    if not workflow_context:
        return ""
    lines: list[str] = []
    if workflow_context.get("work_root"):
        lines.append(f"workflow work_root: {workflow_context['work_root']}")
    if workflow_context.get("default_work_dir"):
        lines.append(f"run_skill work_dir (required): {workflow_context['default_work_dir']}")
    work_root = workflow_context.get("work_root")
    structure_path = workflow_context.get("structure_path")
    if structure_path:
        display_path = structure_path
        if work_root:
            from extensions._core.workflow.workflow_output_paths import path_under_work_root

            display_path = path_under_work_root(str(work_root), str(structure_path))
        lines.append(f"structure/POSCAR file (relative): {display_path}")
    file_refs = workflow_context.get("file_refs")
    if isinstance(file_refs, dict) and file_refs:
        for key, path in file_refs.items():
            display_path = path
            if work_root:
                from extensions._core.workflow.workflow_output_paths import path_under_work_root

                display_path = path_under_work_root(str(work_root), str(path))
            lines.append(f"file ref {key} (relative): {display_path}")
    if workflow_context.get("vasp_config_path"):
        lines.append(f"vasp --config (use in argv if needed): {workflow_context['vasp_config_path']}")
    if not lines:
        return ""
    return "Workflow host paths:\n" + "\n".join(f"- {ln}" for ln in lines) + "\n\n"


async def invoke_workflow_llm_with_tools(
    *,
    llm: Any,
    tools: Sequence[BaseTool],
    prompt: str,
    system_prompt: str | None,
    skill_names: list[str] | None,
    workflow_context: dict[str, Any] | None = None,
    max_tool_rounds: int = 8,
) -> tuple[str, list[ToolMessage]]:
    """Run a short ReAct loop; return final assistant text + tool messages for format_skill_output."""
    final_system = _inject_skills_prompt(system_prompt, skill_names)
    messages: list[BaseMessage] = []
    if final_system:
        messages.append(SystemMessage(content=final_system))
    user_text = _workflow_paths_user_block(workflow_context) + prompt
    messages.append(HumanMessage(content=user_text))

    agent = create_agent(llm, tools=list(tools))
    tool_messages: list[ToolMessage] = []
    state: dict[str, Any] = {"messages": messages}

    for _ in range(max_tool_rounds):
        result = await agent.ainvoke(state)
        if not isinstance(result, dict):
            break
        state = result
        msgs = result.get("messages") or []
        new_tools = [m for m in msgs if isinstance(m, ToolMessage)]
        tool_messages.extend(new_tools)
        last_ai = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        if last_ai and not getattr(last_ai, "tool_calls", None):
            text = last_ai.content if isinstance(last_ai.content, str) else str(last_ai.content)
            return text, tool_messages

    msgs = state.get("messages") or []
    for m in reversed(msgs):
        if isinstance(m, AIMessage):
            text = m.content if isinstance(m.content, str) else str(m.content)
            return text, tool_messages
    return "", tool_messages

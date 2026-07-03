# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json

from extensions._core.workflow.format_skill_output import format_skill_output


def test_no_awaiting_external_without_real_envelope():
    """Top-level status=submitted in tool JSON without async_envelope must not alone trigger detach UI."""
    tool = json.dumps({"exit_code": 1, "status": "submitted", "success": False, "stderr": "fail"})
    out = format_skill_output(
        tool_results=[tool],
        llm_response='{"relax_poscar": ""}',
        output_format="json",
        output_fields=[{"name": "relax_poscar", "type": "File"}],
    )
    payload = out.get("output") or {}
    assert not payload.get("_awaiting_external")


def test_awaiting_external_with_async_envelope_in_tool():
    env = {
        "status": "submitted",
        "task_kind": "vasp_relax",
        "external_ref": "j1",
        "poll_command": "python poll.py",
    }
    tool = json.dumps({"async_envelope": env, "success": False})
    out = format_skill_output(
        tool_results=[tool],
        llm_response='{"relax_poscar": {"file": ""}}',
        output_format="json",
        output_fields=[{"name": "relax_poscar", "type": "File"}],
    )
    assert out["output"].get("_awaiting_external") is True

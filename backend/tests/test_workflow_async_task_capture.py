# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json

from extensions._core.workflow.workflow_async_tasks import (
    capture_envelope_from_tool_output,
    capture_envelope_from_tool_outputs,
)


def test_capture_envelope_from_run_skill_json_wrapper():
    envelope = {
        "status": "submitted",
        "task_kind": "vasp_relax",
        "external_ref": "job-123",
        "poll_command": "python /mnt/skills/public/vasp-relax/scripts/poll.py --work-dir /tmp/w",
        "poll_interval_seconds": 1800,
    }
    tool_json = json.dumps(
        {
            "exit_code": 0,
            "success": False,
            "status": "submitted",
            "async_envelope": envelope,
            "stderr": "logs\n",
            "stdout": "{}",
        },
        ensure_ascii=False,
    )
    got = capture_envelope_from_tool_output(tool_json)
    assert got is not None
    assert got["task_kind"] == "vasp_relax"
    assert got["external_ref"] == "job-123"


def test_capture_envelope_from_tool_outputs_list():
    env = {"status": "submitted", "task_kind": "vasp_relax", "external_ref": "x"}
    texts = [
        json.dumps({"success": False, "async_envelope": env}),
    ]
    assert capture_envelope_from_tool_outputs(texts) == env

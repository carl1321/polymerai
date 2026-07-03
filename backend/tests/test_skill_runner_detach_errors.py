# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from unittest.mock import patch

from extensions._core.workflow.skill_runner import (
    _apply_detach_requirement,
    _normalize_async_envelope_poll_command,
    run_skill,
)


def test_apply_detach_requirement_returns_json_error_not_raise():
    raw = {
        "exit_code": 1,
        "stderr": "ERROR: POSCAR not found",
        "stdout": "",
        "success": False,
    }
    out = _apply_detach_requirement(raw, skill_name="vasp-relax", require_detach=True)
    assert out["detach_error"] is True
    assert out["error_kind"] == "submit_failed"
    assert "did not emit a detach envelope" in out["error"]


def test_apply_detach_requirement_normalizes_poll_command():
    host_public = "/repo/skills/public"
    env = {
        "status": "submitted",
        "poll_command": "python /mnt/skills/public/vasp-relax/scripts/poll.py --work-dir /tmp/w",
    }
    with patch("extensions._core.workflow.skill_runner._skills_repo_root") as mock_root:
        from pathlib import Path

        mock_root.return_value = Path("/repo/skills")
        out = _normalize_async_envelope_poll_command(env)
    assert "/mnt/skills/public" not in out["poll_command"]
    assert "vasp-relax/scripts/poll.py" in out["poll_command"]


def test_run_skill_detach_failure_returns_dict():
    fake_result = {
        "exit_code": 1,
        "stderr": "fail",
        "stdout": "",
        "work_dir": "/tmp/w",
        "success": False,
    }

    with patch("extensions._core.workflow.skill_runner.resolve_skill_dir") as rs:
        from pathlib import Path

        rs.return_value = Path("/fake/vasp-relax")
        with patch("extensions._core.workflow.skill_runner._find_entry_script") as fe:
            fe.return_value = Path("/fake/vasp-relax/scripts/run.py")
            with patch("extensions._core.workflow.skill_runner._run_subprocess", return_value=fake_result):
                out = run_skill("vasp-relax", work_dir="/tmp/w", argv=["x"], require_detach=True)
    assert out.get("detach_error") is True
    assert "error" in out

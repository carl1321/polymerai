# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from extensions._core.workflow.runtime.db import resolve_run_status_from_node_tasks
from extensions._core.workflow.workflow_interrupt import has_interrupt_in_invoke_result


def test_resolve_awaiting_external():
    status, err = resolve_run_status_from_node_tasks(
        [
            {"node_id": "a", "status": "success"},
            {"node_id": "b", "status": "awaiting_external"},
        ],
    )
    assert status == "awaiting_external"
    assert err is None


def test_resolve_failed():
    status, err = resolve_run_status_from_node_tasks(
        [
            {"node_id": "a", "status": "success"},
            {"node_id": "b", "status": "failed", "error": {"error": "vasprun parse failed"}},
        ],
    )
    assert status == "failed"
    assert err is not None
    assert "vasprun" in err["message"]


def test_resolve_success_all_terminal():
    status, _ = resolve_run_status_from_node_tasks(
        [{"node_id": "a", "status": "success"}, {"node_id": "b", "status": "skipped"}],
    )
    assert status == "success"


def test_has_interrupt_in_invoke_result():
    assert has_interrupt_in_invoke_result({"__interrupt__": [{"value": {"x": 1}}]}) is True
    assert has_interrupt_in_invoke_result({"node_outputs": {}}) is False

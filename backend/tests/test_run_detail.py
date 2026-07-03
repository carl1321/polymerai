# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from extensions._core.workflow.run_detail import (
    build_node_index_from_spec,
    enrich_node_tasks,
    resolve_configured_node_name,
)


def test_resolve_configured_node_name_prefers_task_name():
    data = {
        "taskName": "potcar",
        "displayName": "显示用POTCAR",
        "label": "开始",
    }
    assert resolve_configured_node_name("abc123", data) == "potcar"


def test_build_node_index_uses_task_name_not_node_id():
    spec = {
        "nodes": [
            {
                "id": "n1",
                "type": "llm",
                "data": {"taskName": "vasp-potcar", "displayName": "POTCAR生成", "llmSkill": "vasp-potcar"},
            }
        ]
    }
    index = build_node_index_from_spec(spec)
    assert index["n1"]["node_name"] == "vasp-potcar"
    assert index["n1"]["display_name"] == "POTCAR生成"


def test_enrich_node_tasks_sets_node_name():
    tasks = [
        {
            "id": "t1",
            "node_id": "n1",
            "status": "success",
            "input": {"prompt": "hi"},
            "output": {"output": {"success": True}},
            "run_seq": 1,
        }
    ]
    index = {"n1": {"node_name": "vasp-potcar", "type": "llm", "display_name": "POTCAR"}}
    rows = enrich_node_tasks(tasks, index)
    assert rows[0]["node_name"] == "vasp-potcar"

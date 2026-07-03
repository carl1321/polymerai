# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from extensions._core.workflow.compiler import format_node_output


def test_tool_output_only_configured_poscar_field():
    file_ref = {"file": "nodes/t1/outputs/result.POSCAR"}
    fields = [{"name": "POSCAR", "type": "File"}]
    out = format_node_output(file_ref, "json", fields)
    assert out == {"output": {"POSCAR": file_ref}}
    assert set(out["output"].keys()) == {"POSCAR"}


def test_tool_output_dict_strips_extra_keys():
    raw = {
        "POSCAR": {"file": "nodes/t1/POSCAR"},
        "poscar_path": {"file": "nodes/t1/POSCAR"},
        "extra": "drop",
    }
    fields = [{"name": "POSCAR", "type": "File"}]
    out = format_node_output(raw, "json", fields)
    assert set(out["output"].keys()) == {"POSCAR"}

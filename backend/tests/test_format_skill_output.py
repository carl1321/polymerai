# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from extensions._core.workflow.format_skill_output import format_skill_output


def test_skill_output_requires_strict_llm_json(tmp_path):
    work_root = tmp_path / "run"
    work_root.mkdir()
    node_dir = work_root / "nodes" / "potcar"
    node_dir.mkdir(parents=True)
    potcar = node_dir / "POTCAR"
    potcar.write_text("pot\n", encoding="utf-8")

    out = format_skill_output(
        tool_results=['{"exit_code": 0, "POTCAR": "ignored"}'],
        llm_response="not json",
        output_format="json",
        output_fields=[{"name": "POTCAR", "type": "File"}],
        work_dir_hint=str(work_root),
        node_work_dir=str(node_dir),
    )
    payload = out["output"]
    assert payload.get("success") is False
    assert "errors" in payload


def test_skill_output_merges_llm_json_with_tool_file(tmp_path):
    work_root = tmp_path / "run"
    work_root.mkdir()
    node_dir = work_root / "nodes" / "potcar"
    node_dir.mkdir(parents=True)
    potcar = node_dir / "POTCAR"
    potcar.write_text("pot\n", encoding="utf-8")

    llm_json = '{"POTCAR": {"file": ""}}'
    out = format_skill_output(
        tool_results=['{"exit_code": 0}'],
        llm_response=llm_json,
        output_format="json",
        output_fields=[{"name": "POTCAR", "type": "File"}],
        work_dir_hint=str(work_root),
        node_work_dir=str(node_dir),
    )
    assert out["output"]["POTCAR"]["file"] == "nodes/potcar/POTCAR"

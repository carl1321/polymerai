# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from extensions._core.workflow.format_skill_output import format_skill_output
from extensions._core.workflow.runtime.template_parser import render_template


def test_format_skill_output_fallback_from_exec_potcar(tmp_path):
    work_root = str(tmp_path)
    node_dir = tmp_path / "nodes" / "Dtsmet374fo0jFGPn1KHE"
    potcar = node_dir / "POTCAR"
    potcar.parent.mkdir(parents=True)
    potcar.write_text("POTCAR\n", encoding="utf-8")

    out = format_skill_output(
        tool_results=[{"success": True, "exit_code": 0}],
        output_format="json",
        output_fields=[{"name": "POTCAR", "type": "File"}],
        work_dir_hint=work_root,
        node_work_dir=str(node_dir),
        llm_response="I generated the POTCAR file successfully.",
    )
    assert out["output"]["POTCAR"]["file"] == "nodes/Dtsmet374fo0jFGPn1KHE/POTCAR"
    assert "errors" not in out.get("output", {})


def test_format_skill_output_relax_poscar_from_relax_subdir(tmp_path):
    work_root = str(tmp_path)
    node_dir = tmp_path / "nodes" / "relax-node"
    contcar = node_dir / "relax" / "CONTCAR"
    contcar.parent.mkdir(parents=True)
    contcar.write_text("relaxed\n", encoding="utf-8")

    out = format_skill_output(
        tool_results=[{"success": True, "exit_code": 0}],
        output_format="json",
        output_fields=[{"name": "relax_poscar", "type": "File"}],
        work_dir_hint=work_root,
        node_work_dir=str(node_dir),
        llm_response='{"relax_poscar": "CONTCAR"}',
    )
    assert out["output"]["relax_poscar"]["file"] == "nodes/relax-node/relax/CONTCAR"


def test_format_skill_output_rejects_phantom_contcar_string(tmp_path):
    work_root = str(tmp_path)
    node_dir = tmp_path / "nodes" / "relax-node"
    node_dir.mkdir(parents=True)
    out = format_skill_output(
        tool_results=[{"success": False}],
        output_format="json",
        output_fields=[{"name": "relax_poscar", "type": "File"}],
        work_dir_hint=work_root,
        node_work_dir=str(node_dir),
        llm_response='{"relax_poscar": "CONTCAR"}',
    )
    assert out["output"].get("success") is False
    assert "errors" in out["output"]


def test_render_template_relative_file_ref(tmp_path):
    work_root = str(tmp_path)
    poscar = tmp_path / "nodes" / "HJMW" / "POSCAR"
    poscar.parent.mkdir(parents=True)
    poscar.write_text("x\n", encoding="utf-8")
    node_outputs = {
        "HJMW": {
            "output": {"POSCAR": {"file": "nodes/HJMW/POSCAR"}},
        },
    }
    rendered = render_template(
        "{{HJMW.output.POSCAR}}",
        node_outputs,
        {"HJMW": "tool"},
        work_root=work_root,
        file_path_style="relative",
    )
    assert rendered == "nodes/HJMW/POSCAR"
    assert not rendered.startswith("/Users")


def test_render_template_absolute_for_tool_invoke(tmp_path):
    work_root = str(tmp_path)
    poscar = tmp_path / "nodes" / "HJMW" / "POSCAR"
    poscar.parent.mkdir(parents=True)
    poscar.write_text("x\n", encoding="utf-8")
    node_outputs = {
        "HJMW": {
            "output": {"POSCAR": {"file": "nodes/HJMW/POSCAR"}},
        },
    }
    rendered = render_template(
        "{{HJMW.output.POSCAR}}",
        node_outputs,
        {"HJMW": "tool"},
        work_root=work_root,
        file_path_style="absolute",
    )
    assert rendered == str(poscar.resolve())

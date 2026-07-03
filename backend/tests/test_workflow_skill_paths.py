# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from pathlib import Path

from extensions._core.workflow.runtime.template_parser import render_template
from extensions._core.workflow.workflow_skill_paths import (
    build_skill_argv_from_refs,
    default_skill_argv,
    extract_file_refs_from_prompt,
    find_structure_path,
    resolve_workflow_work_dir,
)


def test_resolve_workflow_work_dir_rejects_mnt(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    default = root / "nodes" / "vasp-potcar"
    default.mkdir(parents=True)
    ctx = {
        "work_root": str(root),
        "default_work_dir": str(default),
        "workflow_node_id": "vasp-potcar",
    }
    assert resolve_workflow_work_dir("/mnt/user-data/workflow/step", ctx) == default.resolve()
    assert resolve_workflow_work_dir("", ctx) == default.resolve()


def test_find_structure_path_from_prompt(tmp_path):
    poscar = tmp_path / "POSCAR"
    poscar.write_text("dummy\n", encoding="utf-8")
    found = find_structure_path(node_outputs={}, work_root=None, prompt=str(poscar))
    assert found == str(poscar.resolve())


def test_find_structure_path_nodes_rel_in_prompt_line(tmp_path):
    work_root = tmp_path / "run"
    work_root.mkdir()
    poscar = work_root / "nodes" / "tool1" / "outputs" / "result.POSCAR"
    poscar.parent.mkdir(parents=True)
    poscar.write_text("x\n", encoding="utf-8")
    prompt = "请根据上游输入处理任务：nodes/tool1/outputs/result.POSCAR"
    found = find_structure_path(
        node_outputs={},
        work_root=str(work_root),
        prompt=prompt,
    )
    assert found == str(poscar.resolve())


def test_default_skill_argv_vasp_relax_includes_config(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKFLOW_VASP_DRY_RUN", raising=False)
    poscar = tmp_path / "POSCAR"
    poscar.write_text("x\n", encoding="utf-8")
    wd = tmp_path / "nodes" / "relax"
    wd.mkdir(parents=True)
    argv = default_skill_argv("vasp-relax", str(poscar), wd)
    assert argv[0] == str(poscar)
    assert "--work-dir" in argv
    assert "--config" in argv
    assert "--executor" in argv
    idx = argv.index("--executor")
    assert argv[idx + 1] == "scnet"


def test_extract_file_refs_and_vasp_relax_potcar_argv(tmp_path):
    poscar = tmp_path / "POSCAR"
    poscar.write_text("x\n", encoding="utf-8")
    potcar = tmp_path / "POTCAR"
    potcar.write_text("y\n", encoding="utf-8")
    work_root = str(tmp_path)
    node_outputs = {
        "n_a": {
            "output": {"poscar": {"file": "nodes/a/POSCAR"}},
        },
        "n_b": {
            "output": {"potcar": {"file": "nodes/b/POTCAR"}},
        },
    }
    (tmp_path / "nodes" / "a").mkdir(parents=True)
    (tmp_path / "nodes" / "b").mkdir(parents=True)
    (tmp_path / "nodes" / "a" / "POSCAR").write_text("x\n", encoding="utf-8")
    (tmp_path / "nodes" / "b" / "POTCAR").write_text("y\n", encoding="utf-8")
    node_labels = {"n_a": "POSCAR", "n_b": "POTCAR"}
    prompt = "run {{POSCAR.output.poscar}} with {{POTCAR.output.potcar}}"
    refs = extract_file_refs_from_prompt(
        prompt,
        node_outputs=node_outputs,
        node_labels=node_labels,
        work_root=work_root,
    )
    assert "poscar" in refs
    assert "potcar" in refs
    wd = tmp_path / "nodes" / "relax"
    wd.mkdir(parents=True)
    argv = build_skill_argv_from_refs("vasp-relax", refs["poscar"], wd, refs)
    assert "--potcar" in argv
    assert refs["potcar"] in argv


def test_template_start_input_subkey(tmp_path):
    work_root = str(tmp_path)
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    poscar = inputs_dir / "POSCAR"
    poscar.write_text("x\n", encoding="utf-8")
    node_outputs = {
        "start": {
            "output": {"poscar_path": {"file": "inputs/POSCAR"}},
            "input": {"file": "inputs/POSCAR"},
        },
    }
    rendered = render_template(
        "{{开始.output.poscar_path}}",
        node_outputs,
        {"start": "开始"},
        work_root=work_root,
    )
    assert rendered == str(poscar.resolve())
    rendered_input = render_template(
        "{{开始.input.poscar_path}}",
        node_outputs,
        {"start": "开始"},
        work_root=work_root,
    )
    assert rendered_input == str(poscar.resolve())


def test_default_skill_argv_vasp_potcar(tmp_path):
    poscar = tmp_path / "POSCAR"
    poscar.write_text("x\n", encoding="utf-8")
    wd = tmp_path / "nodes" / "step"
    wd.mkdir(parents=True)
    argv = default_skill_argv("vasp-potcar", str(poscar), wd)
    assert argv[0] == "workflow"
    assert argv[1] == str(poscar)
    assert argv[-1] == str(wd / "POTCAR")

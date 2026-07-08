# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Unit tests for terminal output parsing (output_parser node helpers)."""

from __future__ import annotations

from extensions._core.workflow.terminal_output import (
    build_terminal_output,
    extract_file_manifest,
    extract_primary_result,
    select_saved_node_ids,
)

# --------------------------- extract_primary_result ---------------------------

def test_primary_result_prefers_output():
    assert extract_primary_result({"output": {"a": 1}, "result": "x"}) == {"a": 1}


def test_primary_result_falls_back_to_result():
    assert extract_primary_result({"result": True, "conditionResult": True}) is True


def test_primary_result_returns_whole_when_no_keys():
    payload = {"foo": "bar"}
    assert extract_primary_result(payload) == payload


def test_primary_result_non_dict():
    assert extract_primary_result("hello") == "hello"


# --------------------------- extract_file_manifest ---------------------------

def test_manifest_resolves_existing_file(tmp_path):
    work_root = tmp_path
    (work_root / "nodes" / "nodeA" / "outputs").mkdir(parents=True)
    contcar = work_root / "nodes" / "nodeA" / "outputs" / "CONTCAR"
    contcar.write_text("POSCAR data")

    node_output = {"output": {"poscar_path": {"file": "nodes/nodeA/outputs/CONTCAR"}}}
    manifest = extract_file_manifest(node_output, str(work_root))

    assert len(manifest) == 1
    item = manifest[0]
    assert item["field"] == "output.poscar_path"
    assert item["filename"] == "CONTCAR"
    assert item["relative_path"] == "nodes/nodeA/outputs/CONTCAR"
    assert item["absolute_path"] == str(contcar.resolve())
    assert item["exists"] is True
    assert item["size"] == len("POSCAR data")


def test_manifest_marks_missing_file(tmp_path):
    node_output = {"output": {"f": {"file": "nodes/x/missing.dat"}}}
    manifest = extract_file_manifest(node_output, str(tmp_path))
    assert len(manifest) == 1
    assert manifest[0]["exists"] is False
    assert manifest[0]["size"] is None


def test_manifest_finds_files_in_lists_and_nested(tmp_path):
    node_output = {
        "output": [
            {"file": "a.txt"},
            {"nested": {"file": "b.txt"}},
        ]
    }
    manifest = extract_file_manifest(node_output, str(tmp_path))
    fields = {m["field"] for m in manifest}
    assert fields == {"output[0]", "output[1].nested"}


def test_manifest_empty_when_no_files():
    assert extract_file_manifest({"output": {"score": 0.9}}, None) == []


# --------------------------- select_saved_node_ids ---------------------------

def test_select_save_all_excludes_self():
    outputs = {"a": {}, "b": {}, "parser": {}}
    assert select_saved_node_ids(outputs, "parser", True, None) == ["a", "b"]


def test_select_defaults_to_all_when_nothing_specified():
    outputs = {"a": {}, "b": {}, "parser": {}}
    assert select_saved_node_ids(outputs, "parser", None, None) == ["a", "b"]


def test_select_explicit_ids_preserve_order_and_filter_missing():
    outputs = {"a": {}, "b": {}, "parser": {}}
    assert select_saved_node_ids(outputs, "parser", False, ["b", "zzz", "a"]) == ["b", "a"]


def test_select_explicit_ids_exclude_self():
    outputs = {"a": {}, "parser": {}}
    assert select_saved_node_ids(outputs, "parser", False, ["a", "parser"]) == ["a"]


# --------------------------- build_terminal_output ---------------------------

def test_build_terminal_output_structure(tmp_path):
    (tmp_path / "out").mkdir()
    f = tmp_path / "out" / "res.json"
    f.write_text("{}")

    node_outputs = {
        "llm1": {"output": {"answer": "hi"}, "resolved_inputs": {"prompt": "p"}},
        "tool1": {"result": 42, "output": {"file_out": {"file": "out/res.json"}}},
        "cond1": {"result": True, "conditionResult": True},
        "parser": {},
    }
    node_meta = {
        "llm1": {"node_name": "问答", "node_type": "llm", "skill": None},
        "tool1": {"node_name": "计算", "node_type": "tool", "skill": "vasp-relax"},
        "cond1": {"node_name": "判断", "node_type": "condition", "skill": None},
    }

    result = build_terminal_output(["llm1", "tool1", "cond1"], node_outputs, node_meta, str(tmp_path))
    term = result["__terminal__"]

    assert term["schema_version"] == 1
    assert term["saved_node_ids"] == ["llm1", "tool1", "cond1"]
    assert len(term["nodes"]) == 3
    assert term["file_count"] == 1

    by_id = {n["node_id"]: n for n in term["nodes"]}
    assert by_id["llm1"]["result"] == {"answer": "hi"}
    assert by_id["llm1"]["node_name"] == "问答"
    assert by_id["tool1"]["result"] == {"file_out": {"file": "out/res.json"}}
    assert by_id["tool1"]["skill"] == "vasp-relax"
    assert by_id["tool1"]["files"][0]["exists"] is True
    assert by_id["cond1"]["result"] is True
    assert by_id["cond1"]["files"] == []


def test_build_terminal_output_missing_meta_uses_node_id(tmp_path):
    node_outputs = {"n1": {"output": 1}}
    result = build_terminal_output(["n1"], node_outputs, {}, None)
    node = result["__terminal__"]["nodes"][0]
    assert node["node_name"] == "n1"
    assert node["node_type"] == ""

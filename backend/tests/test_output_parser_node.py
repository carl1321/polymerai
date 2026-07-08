# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Integration test: compile and run a workflow with an output_parser node.

Runs a minimal start -> output_parser -> end graph through LangGraph with no DB
state manager and no LLM, verifying the terminal parser collects upstream node
outputs and produces the unified __terminal__ structure in node_outputs.
"""

from __future__ import annotations

import pytest

from extensions._core.workflow.compiler import compile_workflow_to_langgraph
from extensions._core.workflow.workflow_request import WorkflowConfigRequest


def _node(node_id: str, node_type: str, data: dict) -> dict:
    return {"id": node_id, "type": node_type, "position": {"x": 0.0, "y": 0.0}, "data": data}


def _edge(source: str, target: str) -> dict:
    return {"id": f"{source}->{target}", "source": source, "target": target}


@pytest.mark.asyncio
async def test_output_parser_collects_upstream_outputs(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "CONTCAR").write_text("structure")

    spec = {
        "name": "wf-terminal-test",
        "nodes": [
            _node("start1", "start", {"label": "开始"}),
            _node("parser1", "output_parser", {"label": "终态解析", "saveAll": True}),
            _node("end1", "end", {"label": "结束"}),
        ],
        "edges": [
            _edge("start1", "parser1"),
            _edge("parser1", "end1"),
        ],
    }
    config = WorkflowConfigRequest.model_validate(spec)
    graph = compile_workflow_to_langgraph(config, checkpointer=None)

    result = await graph.ainvoke(
        {
            "workflow_inputs": {"input": "hello", "work_root": str(tmp_path)},
            "node_outputs": {},
        },
        config={"configurable": {"thread_id": "test-thread"}},
    )

    node_outputs = result["node_outputs"]
    assert "parser1" in node_outputs
    term = node_outputs["parser1"]["__terminal__"]
    assert term["schema_version"] == 1
    # start1 executed before the parser, so it must be captured; parser excludes itself
    assert "start1" in term["saved_node_ids"]
    assert "parser1" not in term["saved_node_ids"]
    start_entry = next(n for n in term["nodes"] if n["node_id"] == "start1")
    assert start_entry["node_type"] == "start"
    assert "result" in start_entry


@pytest.mark.asyncio
async def test_output_parser_respects_explicit_selection(tmp_path):
    spec = {
        "name": "wf-terminal-select",
        "nodes": [
            _node("start1", "start", {"label": "开始"}),
            _node(
                "parser1",
                "output_parser",
                {"label": "终态解析", "saveAll": False, "saveNodeIds": ["does-not-exist"]},
            ),
            _node("end1", "end", {"label": "结束"}),
        ],
        "edges": [
            _edge("start1", "parser1"),
            _edge("parser1", "end1"),
        ],
    }
    config = WorkflowConfigRequest.model_validate(spec)
    graph = compile_workflow_to_langgraph(config, checkpointer=None)

    result = await graph.ainvoke(
        {"workflow_inputs": {"input": "x", "work_root": str(tmp_path)}, "node_outputs": {}},
        config={"configurable": {"thread_id": "test-thread-2"}},
    )

    term = result["node_outputs"]["parser1"]["__terminal__"]
    # explicit list referenced only a missing node -> nothing saved
    assert term["saved_node_ids"] == []
    assert term["nodes"] == []

# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

from extensions._core.workflow.workflow_interrupt import (
    is_interrupt_error_message,
    is_workflow_interrupt,
    workflow_interrupt_detail,
)


def test_is_workflow_interrupt_graph_interrupt():
    exc = GraphInterrupt((Interrupt(value={"async_task_id": "x", "node_id": "n1"}),))
    assert is_workflow_interrupt(exc) is True
    assert workflow_interrupt_detail(exc) == {"async_task_id": "x", "node_id": "n1"}


def test_is_workflow_interrupt_normal_error():
    assert is_workflow_interrupt(RuntimeError("boom")) is False


def test_is_interrupt_error_message():
    msg = "(Interrupt(value={'async_task_id': 'x', 'node_id': 'n1'}, id='abc'),)"
    assert is_interrupt_error_message(msg) is True
    assert is_interrupt_error_message("boom") is False

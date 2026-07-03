# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from extensions._core.workflow.runtime.node_labels import (
    node_label_from_data,
    read_node_data_field,
)


def test_read_node_data_field_importable():
    assert read_node_data_field({"displayName": "上游"}, "display_name", "displayName") == "上游"
    assert node_label_from_data({"taskName": "tool"}, "id1") == "tool"

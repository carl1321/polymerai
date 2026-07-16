// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { NodeTypes } from "@xyflow/react";

import { ConditionNode } from "../editor/nodes/ConditionNode";
import { EndNode } from "../editor/nodes/EndNode";
import { LLMNode } from "../editor/nodes/LLMNode";
import { LoopNode } from "../editor/nodes/LoopNode";
import { StartNode } from "../editor/nodes/StartNode";
import { ToolNode } from "../editor/nodes/ToolNode";

export const workflowNodeTypes: NodeTypes = {
  start: StartNode,
  end: EndNode,
  llm: LLMNode,
  tool: ToolNode,
  condition: ConditionNode,
  loop: LoopNode,
};

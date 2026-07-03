// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { NodeTypes } from "@xyflow/react";
import { StartNode } from "../editor/nodes/StartNode";
import { EndNode } from "../editor/nodes/EndNode";
import { LLMNode } from "../editor/nodes/LLMNode";
import { ToolNode } from "../editor/nodes/ToolNode";
import { ConditionNode } from "../editor/nodes/ConditionNode";
import { LoopNode } from "../editor/nodes/LoopNode";

export const workflowNodeTypes: NodeTypes = {
  start: StartNode,
  end: EndNode,
  llm: LLMNode,
  tool: ToolNode,
  condition: ConditionNode,
  loop: LoopNode,
};

// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
} from "@xyflow/react";
import type { Node } from "@xyflow/react";
import { useCallback, useEffect, useMemo } from "react";
import "@xyflow/react/dist/style.css";

import { buildGraphFromReleaseSpec } from "@/components/workflow/graph/workflow-graph-utils";
import { workflowNodeTypes } from "@/components/workflow/graph/workflow-node-types";
import type { WorkflowRunDetail } from "@/core/api/workflows";

type RunExecutionGraphProps = {
  detail: WorkflowRunDetail;
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string) => void;
};

function RunExecutionGraphInner({
  detail,
  selectedNodeId,
  onSelectNode,
}: RunExecutionGraphProps) {
  const { fitView } = useReactFlow();

  const { nodes, edges } = useMemo(
    () => buildGraphFromReleaseSpec(detail.release_spec, detail.nodes),
    [detail.release_spec, detail.nodes],
  );

  const displayNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: n.id === selectedNodeId,
      })),
    [nodes, selectedNodeId],
  );

  useEffect(() => {
    if (nodes.length === 0) return;
    const t = window.setTimeout(() => {
      void fitView({ padding: 0.2, duration: 200 });
    }, 50);
    return () => window.clearTimeout(t);
  }, [nodes.length, fitView]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onSelectNode?.(node.id);
    },
    [onSelectNode],
  );

  if (!detail.release_spec?.nodes?.length) {
    return (
      <div className="bg-muted/20 text-muted-foreground flex h-[420px] items-center justify-center rounded-md border border-dashed text-sm">
        该运行无发布版本图，无法还原流程图
      </div>
    );
  }

  return (
    <div className="bg-app h-[420px] w-full overflow-hidden rounded-md border">
      <ReactFlow
        nodes={displayNodes}
        edges={edges}
        nodeTypes={workflowNodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        zoomOnScroll
        deleteKeyCode={null}
        onNodeClick={onNodeClick}
        fitView
        attributionPosition="bottom-left"
      >
        <Controls showInteractive={false} />
        <MiniMap zoomable pannable />
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
      </ReactFlow>
    </div>
  );
}

export function RunExecutionGraph(props: RunExecutionGraphProps) {
  return (
    <ReactFlowProvider>
      <RunExecutionGraphInner {...props} />
    </ReactFlowProvider>
  );
}

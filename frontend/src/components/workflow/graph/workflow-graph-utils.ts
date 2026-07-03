// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { Edge, Node } from "@xyflow/react";
import type { WorkflowRunNodeExecution } from "@/core/api/workflows";

export const LOOP_PADDING = {
  top: 65,
  right: 16,
  bottom: 20,
  left: 16,
};

export type ExecutionStatus =
  | "pending"
  | "ready"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "cancelled";

export function mapRunTaskStatusToExecutionStatus(status: string): ExecutionStatus {
  const st = String(status || "").toLowerCase();
  if (st === "pending") return "ready";
  if (st === "running" || st === "awaiting_external") return "running";
  if (st === "success") return "success";
  if (st === "failed") return "error";
  if (st === "skipped") return "skipped";
  if (st === "cancelled" || st === "canceled") return "cancelled";
  return "ready";
}

export function normalizeNodesData(nodes: Node[]): Node[] {
  return nodes.map((node) => {
    const nodeData = node.data || {};

    let taskName: string;
    let displayName: string;

    if (nodeData.taskName) {
      taskName = typeof nodeData.taskName === "string" ? nodeData.taskName : String(nodeData.taskName);
    } else if (nodeData.nodeName) {
      taskName = typeof nodeData.nodeName === "string" ? nodeData.nodeName : String(nodeData.nodeName);
    } else {
      if (node.type === "start") {
        taskName = "start";
      } else if (node.type === "end") {
        taskName = "end";
      } else if (node.type === "tool") {
        const sameTypeNodes = nodes.filter((n) => n.type === "tool");
        const index = sameTypeNodes.findIndex((n) => n.id === node.id);
        taskName = index === 0 ? "tool" : `tool${index}`;
      } else {
        const sameTypeNodes = nodes.filter((n) => n.type === node.type);
        const typeLabels: Record<string, string> = {
          llm: "LLM",
          condition: "条件",
          loop: "loop",
        };
        const baseName = typeLabels[node.type || ""] || node.type || "节点";
        const index = sameTypeNodes.findIndex((n) => n.id === node.id);
        taskName = index === 0 ? baseName : `${baseName}${index}`;
      }
    }

    if (node.type === "tool" && (taskName === "工具" || taskName.startsWith("工具"))) {
      taskName = taskName === "工具" ? "tool" : `tool${taskName.slice(2)}`;
    }

    if (node.type === "start") {
      displayName = "开始";
    } else if (node.type === "end") {
      displayName = "结束";
    } else if (node.type === "tool") {
      displayName =
        typeof nodeData.displayName === "string" && nodeData.displayName.trim()
          ? nodeData.displayName
          : "工具";
    } else {
      displayName =
        typeof nodeData.displayName === "string"
          ? nodeData.displayName
          : typeof nodeData.label === "string"
            ? nodeData.label
            : taskName;
    }

    const normalizedLabel = String(displayName);

    return {
      ...node,
      label: normalizedLabel,
      data: {
        ...nodeData,
        taskName: String(taskName),
        nodeName: undefined,
        displayName: String(displayName),
        label: normalizedLabel,
      },
    };
  });
}

export function processNodesLayout(nodes: Node[]): Node[] {
  const normalized = normalizeNodesData(nodes);

  return normalized.map((node) => {
    if (node.type === "loop") {
      const loopWidthRaw = node.data?.loopWidth ?? node.data?.loop_width;
      const loopHeightRaw = node.data?.loopHeight ?? node.data?.loop_height;
      const loopWidthNum = typeof loopWidthRaw === "number" ? loopWidthRaw : Number(loopWidthRaw);
      const loopHeightNum = typeof loopHeightRaw === "number" ? loopHeightRaw : Number(loopHeightRaw);
      const loopWidth = Number.isFinite(loopWidthNum) ? loopWidthNum : 600;
      const loopHeight = Number.isFinite(loopHeightNum) ? loopHeightNum : 400;
      return {
        ...node,
        width: loopWidth,
        height: loopHeight,
        style: {
          ...(node.style || {}),
          pointerEvents: "auto",
          zIndex: (node.style as { zIndex?: number })?.zIndex ?? 1,
        },
      };
    }

    const loopId = node.data?.loopId || node.data?.loop_id;
    if (!loopId) {
      if (node.parentId) {
        return {
          ...node,
          parentId: undefined,
          extent: undefined,
          data: {
            ...node.data,
            isLoopChild: undefined,
          },
        };
      }
      return node;
    }

    const loopNode = normalized.find((n) => n.id === loopId && n.type === "loop");
    if (!loopNode) {
      return {
        ...node,
        parentId: undefined,
        extent: undefined,
        data: {
          ...node.data,
          loopId: undefined,
          loop_id: undefined,
          isLoopChild: undefined,
        },
      };
    }

    let position = node.position;

    if (node.parentId !== loopNode.id) {
      const relativeX = node.position.x - loopNode.position.x - LOOP_PADDING.left;
      const relativeY = node.position.y - loopNode.position.y - LOOP_PADDING.top;
      position = {
        x: LOOP_PADDING.left + Math.max(0, relativeX),
        y: LOOP_PADDING.top + Math.max(0, relativeY),
      };
    }

    return {
      ...node,
      parentId: loopNode.id,
      position,
      extent: "parent",
      draggable: true,
      style: {
        ...node.style,
        zIndex: 15,
        pointerEvents: "auto",
      },
      data: {
        ...node.data,
        isLoopChild: true,
      },
    };
  });
}

export function specToFlowNodes(specNodes: unknown[] | undefined): Node[] {
  if (!Array.isArray(specNodes)) return [];
  return specNodes.map((raw) => {
    const n = raw as Record<string, unknown>;
    const pos = n.position as { x?: number; y?: number } | undefined;
    return {
      id: String(n.id),
      type: String(n.type),
      position: { x: Number(pos?.x ?? 0), y: Number(pos?.y ?? 0) },
      data: (n.data as Record<string, unknown>) ?? {},
    } as Node;
  });
}

export function specToFlowEdges(specEdges: unknown[] | undefined): Edge[] {
  if (!Array.isArray(specEdges)) return [];
  return specEdges.map((raw) => {
    const e = raw as Record<string, unknown>;
    return {
      id: String(e.id),
      source: String(e.source),
      target: String(e.target),
      sourceHandle: (e.sourceHandle ?? e.source_handle) as string | undefined,
      targetHandle: (e.targetHandle ?? e.target_handle) as string | undefined,
    } as Edge;
  });
}

export function buildExecutionOverlayNodes(
  baseNodes: Node[],
  executions: WorkflowRunNodeExecution[],
): Node[] {
  const byNodeId = new Map<string, WorkflowRunNodeExecution>();
  for (const ex of executions) {
    byNodeId.set(String(ex.node_id), ex);
  }

  return baseNodes.map((node) => {
    const task = byNodeId.get(node.id);
    if (!task) {
      return {
        ...node,
        data: {
          ...node.data,
          executionStatus: "ready" as ExecutionStatus,
        },
      };
    }
    return {
      ...node,
      data: {
        ...node.data,
        executionStatus: mapRunTaskStatusToExecutionStatus(task.status),
        executionResult: {
          outputs: task.output,
          error: task.error,
          metrics: task.metrics,
          startTime: task.started_at,
          endTime: task.finished_at,
        },
      },
    };
  });
}

export function buildGraphFromReleaseSpec(
  spec: { nodes?: unknown[]; edges?: unknown[] } | null | undefined,
  executions: WorkflowRunNodeExecution[] | null | undefined,
): { nodes: Node[]; edges: Edge[] } {
  const flowNodes = processNodesLayout(specToFlowNodes(spec?.nodes));
  const nodes = buildExecutionOverlayNodes(flowNodes, executions ?? []);
  const edges = specToFlowEdges(spec?.edges);
  return { nodes, edges };
}

export const ACTIVE_RUN_STATUSES = new Set(["running", "queued", "awaiting_external"]);

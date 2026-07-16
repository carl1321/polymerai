// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Wrench, Loader2, CheckCircle2, XCircle } from "lucide-react";

import { cn } from "~/lib/utils";

type ExecutionStatus =
  | "pending"
  | "ready"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "cancelled";

type ToolNodeData = {
  executionStatus?: ExecutionStatus;
  executionResult?: {
    startTime?: number | string;
    endTime?: number | string;
    outputs?: unknown;
    error?: unknown;
  };
  displayName?: string;
  label?: string;
  toolName?: string;
  tool_name?: string;
};
type ToolNodeType = Node<ToolNodeData>;

export function ToolNode({ data, selected }: NodeProps<ToolNodeType>) {
  const executionStatus: ExecutionStatus = data.executionStatus ?? "pending";
  const statusColors = {
    pending: "border-purple-500",
    // ready：默认初始态，不闪烁
    ready: "border-blue-500",
    running: "border-yellow-500",
    success: "border-green-500",
    error: "border-red-500",
    skipped: "border-gray-400",
    cancelled: "border-gray-500",
  };

  const borderColor = selected
    ? "border-primary shadow-md"
    : `${statusColors[executionStatus] || statusColors.pending} hover:border-purple-600`;

  const statusIcons = {
    pending: null,
    ready: null,
    running: <Loader2 className="h-2.5 w-2.5 animate-spin text-yellow-500" />,
    success: <CheckCircle2 className="h-2.5 w-2.5 text-green-500" />,
    error: <XCircle className="h-2.5 w-2.5 text-red-500" />,
    skipped: <span className="text-[10px] text-gray-500">⏭</span>,
    cancelled: <span className="text-[10px] text-gray-500">✕</span>,
  };

  const result = data.executionResult;
  const duration =
    result?.startTime && result?.endTime
      ? (
          (new Date(result.endTime).getTime() -
            new Date(result.startTime).getTime()) /
          1000
        ).toFixed(2) + "s"
      : null;

  return (
    <div
      className={cn(
        "bg-card rounded-lg border-2 p-1.5 shadow-sm transition-all",
        borderColor,
      )}
      style={{ width: "160px" }}
    >
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded bg-purple-100 dark:bg-purple-900/30">
          <Wrench className="h-2.5 w-2.5 text-purple-600 dark:text-purple-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1">
            <div className="text-foreground flex-1 truncate text-xs font-semibold">
              {data.displayName || data.label || "工具"}
            </div>
            {statusIcons[executionStatus]}
          </div>
          <div className="text-muted-foreground flex justify-between truncate text-[10px]">
            <span>{data.toolName}</span>
            {duration && <span>{duration}</span>}
          </div>
        </div>
      </div>
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-muted-foreground !border-card !h-2.5 !w-2.5 !cursor-crosshair !border-2"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-muted-foreground !border-card !h-2.5 !w-2.5 !cursor-crosshair !border-2"
      />
    </div>
  );
}

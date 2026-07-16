// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Square, Loader2, CheckCircle2, XCircle } from "lucide-react";

import { cn } from "~/lib/utils";

type ExecutionStatus =
  | "pending"
  | "ready"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "cancelled";

type EndNodeData = {
  executionStatus?: ExecutionStatus;
  executionResult?: {
    startTime?: number;
    endTime?: number;
    outputs?: unknown;
  };
  displayName?: string;
  label?: string;
};
type EndNodeType = Node<EndNodeData>;

export function EndNode({ data, selected }: NodeProps<EndNodeType>) {
  const executionStatus: ExecutionStatus = data.executionStatus ?? "pending";
  const statusColors = {
    pending: "border-red-500",
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
    : `${statusColors[executionStatus] || statusColors.pending} hover:border-red-600`;

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
      style={{ width: "140px" }}
    >
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded bg-red-100 dark:bg-red-900/30">
          <Square className="h-2.5 w-2.5 text-red-600 dark:text-red-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1">
            <div className="text-foreground flex-1 truncate text-xs font-semibold">
              {data.displayName || data.label || "结束"}
            </div>
            {statusIcons[executionStatus]}
          </div>
          {duration && (
            <div className="text-muted-foreground text-right text-[10px]">
              {duration}
            </div>
          )}
        </div>
      </div>
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-muted-foreground !border-card !h-2.5 !w-2.5 !cursor-crosshair !border-2"
      />
    </div>
  );
}

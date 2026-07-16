// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Brain, Loader2, CheckCircle2, XCircle } from "lucide-react";

import { cn } from "~/lib/utils";

// 简单的执行状态类型
type ExecutionStatus =
  | "pending"
  | "ready"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "cancelled";

type LLMNodeData = {
  executionStatus?: ExecutionStatus;
  executionResult?: {
    startTime?: number | string;
    endTime?: number | string;
    outputs?: unknown;
    error?: unknown;
    metrics?: { total_tokens?: number };
  };
  llmModel?: string;
  llmSkill?: string | null;
  llm_skill?: string | null;
  displayName?: string;
  label?: string;
};
type LLMNodeType = Node<LLMNodeData>;

export function LLMNode({ data, selected }: NodeProps<LLMNodeType>) {
  const executionStatus: ExecutionStatus = data.executionStatus ?? "pending";
  const statusColors = {
    pending: "border-border",
    // ready 是“未执行但可执行”的初始态，不应该闪烁、也不应该显示图标
    ready: "border-blue-500",
    running: "border-yellow-500",
    success: "border-green-500",
    error: "border-red-500",
    skipped: "border-gray-400",
    cancelled: "border-gray-500",
  };

  const borderColor = selected
    ? "border-primary shadow-md"
    : `${statusColors[executionStatus] || statusColors.pending} hover:border-purple-400`;

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
  const tokens = result?.metrics?.total_tokens;
  const hasResult = !!(
    result &&
    (result.outputs != null || result.error != null)
  );

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
          <Brain className="h-2.5 w-2.5 text-purple-600 dark:text-purple-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1">
            <div className="text-foreground flex-1 truncate text-xs font-semibold">
              {data.displayName || data.label || "LLM"}
            </div>
            {statusIcons[executionStatus]}
          </div>
          <div className="text-muted-foreground truncate text-[10px]">
            {data.llmSkill || data.llm_skill || "未绑定技能"}
          </div>
          <div className="text-muted-foreground flex justify-between truncate text-[10px]">
            <span>{data.llmModel || "未选择模型"}</span>
            {duration && <span className="font-medium">{duration}</span>}
          </div>
          {tokens && (
            <div className="text-muted-foreground text-right text-[10px]">
              {tokens} tokens
            </div>
          )}
          {hasResult && executionStatus === "success" && (
            <div
              className="mt-1 truncate text-[10px] text-green-600 dark:text-green-400"
              title="点击查看运行结果"
            >
              ✓ 执行完成
            </div>
          )}
          {hasResult && executionStatus === "error" && (
            <div
              className="mt-1 truncate text-[10px] text-red-600 dark:text-red-400"
              title="点击查看错误信息"
            >
              ✗ 执行失败
            </div>
          )}
        </div>
      </div>
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        className="!bg-muted-foreground !border-card !h-2.5 !w-2.5 !cursor-crosshair !border-2"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        className="!bg-muted-foreground !border-card !h-2.5 !w-2.5 !cursor-crosshair !border-2"
      />
    </div>
  );
}

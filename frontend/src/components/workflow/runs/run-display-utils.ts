// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { ACTIVE_RUN_STATUSES } from "@/components/workflow/graph/workflow-graph-utils";
import type { WorkflowRunDetail } from "@/core/api/workflows";

export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString("zh-CN");
  } catch {
    return String(value);
  }
}

export function formatDurationMs(ms?: number | null): string {
  if (ms == null || ms < 0) return "-";
  if (ms < 1000) return `${ms} ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(2)} s`;
  const min = Math.floor(sec / 60);
  const rem = Math.round(sec % 60);
  return `${min} m ${rem} s`;
}

export function runStatusLabel(status: string): string {
  const map: Record<string, string> = {
    success: "成功",
    failed: "失败",
    running: "运行中",
    queued: "排队中",
    canceled: "已取消",
    cancelled: "已取消",
    awaiting_external: "挂起中（等待外部任务）",
    pending: "待执行",
    skipped: "已跳过",
    awaiting_callback: "等待回调",
    succeeded: "已完成",
    timeout: "超时",
  };
  return map[status] ?? status;
}

export function asyncTaskStatusLabel(status: string): string {
  if (status === "queued") return "等待轮询";
  if (status === "running") return "HPC 执行中";
  return runStatusLabel(status);
}

const ASYNC_TASK_TERMINAL = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "timeout",
]);

export function hasActiveAsyncTasks(
  tasks: { status: string }[] | null | undefined,
): boolean {
  return (tasks ?? []).some((t) => !ASYNC_TASK_TERMINAL.has(String(t.status)));
}

const NODE_ACTIVE_STATUSES = new Set([
  "pending",
  "ready",
  "running",
  "awaiting_external",
]);
const NODE_TERMINAL_OK = new Set(["success", "skipped"]);

/** Run is done only when workflow status and every node task are terminal. */
export function isWorkflowRunComplete(
  runStatus: string,
  nodeTasks: { status: string }[],
): boolean {
  const st = String(runStatus || "");
  if (ACTIVE_RUN_STATUSES.has(st)) return false;
  if (nodeTasks.some((t) => NODE_ACTIVE_STATUSES.has(String(t.status))))
    return false;
  if (st === "success") {
    return (
      nodeTasks.length === 0 ||
      nodeTasks.every((t) => NODE_TERMINAL_OK.has(String(t.status)))
    );
  }
  return st === "failed" || st === "canceled" || st === "cancelled";
}

export function shouldPollRunProgress(
  detail: WorkflowRunDetail | null,
): boolean {
  if (!detail) return false;
  const runStatus = String(detail.run?.status ?? "");
  const nodes = detail.nodes ?? [];
  if (!isWorkflowRunComplete(runStatus, nodes)) return true;
  return hasActiveAsyncTasks(detail.async_tasks);
}

export function isWorkflowSuspendedStatus(status: string): boolean {
  return status === "awaiting_external";
}

export function runStatusBadgeVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "failed" || status === "timeout") return "destructive";
  if (status === "succeeded" || status === "success") return "default";
  if (status === "queued" || status === "running") return "secondary";
  if (isWorkflowSuspendedStatus(status)) return "secondary";
  if (status === "canceled" || status === "cancelled") return "outline";
  return "default";
}

export function formatJson(value: unknown): string {
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string" && !value.trim()) return true;
  if (
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length === 0
  ) {
    return true;
  }
  return false;
}

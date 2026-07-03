// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Badge } from "@/components/ui/badge";
import type { WorkflowRunAsyncTask } from "@/core/api/workflows";
import {
  asyncTaskStatusLabel,
  formatDateTime,
  runStatusBadgeVariant,
} from "./run-display-utils";

type AsyncTaskTableProps = {
  tasks: WorkflowRunAsyncTask[];
};

export function AsyncTaskTable({ tasks }: AsyncTaskTableProps) {
  const rows = tasks ?? [];
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">本次运行无 detach 异步任务（如 VASP HPC 提交）</p>;
  }

  return (
    <div className="rounded-md border overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/30 text-left text-xs text-muted-foreground">
            <th className="p-3 font-medium">任务名称</th>
            <th className="p-3 font-medium">job_id</th>
            <th className="p-3 font-medium">状态</th>
            <th className="p-3 font-medium">开始时间</th>
            <th className="p-3 font-medium">完成时间</th>
            <th className="p-3 font-medium">下次轮询</th>
            <th className="p-3 font-medium">关联节点</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((task) => (
            <tr key={task.id} className="border-b last:border-0">
              <td className="p-3 font-medium">{task.task_name}</td>
              <td className="p-3 font-mono text-xs max-w-[200px] truncate" title={task.job_id ?? ""}>
                {task.job_id ?? "-"}
              </td>
              <td className="p-3">
                <Badge variant={runStatusBadgeVariant(task.status)}>
                  {asyncTaskStatusLabel(task.status)}
                </Badge>
              </td>
              <td className="p-3 text-xs whitespace-nowrap">{formatDateTime(task.started_at)}</td>
              <td className="p-3 text-xs whitespace-nowrap">{formatDateTime(task.finished_at)}</td>
              <td className="p-3 text-xs whitespace-nowrap">{formatDateTime(task.next_poll_at)}</td>
              <td className="p-3">
                <div>{task.node_name ?? "-"}</div>
                {task.workflow_node_id ? (
                  <span className="text-[10px] text-muted-foreground font-mono">{task.workflow_node_id}</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

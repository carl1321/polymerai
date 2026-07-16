// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import type { WorkflowRunNodeExecution } from "@/core/api/workflows";
import { cn } from "@/lib/utils";

import { JsonBlock } from "./JsonBlock";
import {
  formatDateTime,
  formatDurationMs,
  runStatusBadgeVariant,
  runStatusLabel,
} from "./run-display-utils";

type NodeExecutionTableProps = {
  nodes: WorkflowRunNodeExecution[];
  highlightNodeId?: string | null;
  openValues?: string[];
  onOpenValuesChange?: (values: string[]) => void;
};

export function NodeExecutionTable({
  nodes,
  highlightNodeId,
  openValues,
  onOpenValuesChange,
}: NodeExecutionTableProps) {
  if (nodes.length === 0) {
    return <p className="text-muted-foreground text-sm">暂无节点执行记录</p>;
  }

  return (
    <Accordion
      type="multiple"
      className="w-full space-y-2"
      value={openValues}
      onValueChange={onOpenValuesChange}
    >
      {nodes.map((node) => (
        <AccordionItem
          key={node.id}
          value={node.id}
          id={`node-exec-${node.node_id}`}
          className={cn(
            "scroll-mt-24 rounded-md border border-b-0 px-3",
            highlightNodeId === node.node_id &&
              "ring-primary ring-2 ring-offset-2",
          )}
        >
          <AccordionTrigger className="py-3 hover:no-underline">
            <div className="flex flex-1 flex-wrap items-center gap-2 text-left">
              <span className="font-medium">{node.node_name}</span>
              {node.display_name && node.display_name !== node.node_name ? (
                <span className="text-muted-foreground text-xs">
                  （{node.display_name}）
                </span>
              ) : null}
              <Badge variant="outline" className="text-xs">
                {node.node_type || "node"}
              </Badge>
              {node.skill ? (
                <Badge variant="secondary" className="text-xs">
                  {node.skill}
                </Badge>
              ) : null}
              <Badge variant={runStatusBadgeVariant(node.status)}>
                {runStatusLabel(node.status)}
              </Badge>
              <span className="text-muted-foreground mr-2 ml-auto text-xs">
                {formatDateTime(node.started_at)} →{" "}
                {formatDateTime(node.finished_at)}
                {node.duration_ms != null
                  ? ` · ${formatDurationMs(node.duration_ms)}`
                  : ""}
              </span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-3 pb-4">
            <p className="text-muted-foreground font-mono text-[10px]">
              ID: {node.node_id}
            </p>
            <JsonBlock label="输入" value={node.input} />
            <JsonBlock label="输出" value={node.output} />
            {node.error ? <JsonBlock label="错误" value={node.error} /> : null}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}

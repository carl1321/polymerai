// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import type { Node, Edge } from "@xyflow/react";
import {
  ChevronRight,
  ChevronDown,
  Play,
  Brain,
  Wrench,
  GitBranch,
  RotateCcw,
  Database,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "~/components/ui/button";
import { ScrollArea } from "~/components/ui/scroll-area";
import { cn } from "~/lib/utils";

import {
  getDirectUpstreamNodeIds,
  getNodeIdentifier,
  getTransitiveUpstreamNodes,
} from "../utils/upstream";

interface UpstreamNodeSelectorProps {
  currentNodeId: string;
  nodes: Node[];
  edges: Edge[];
  onSelect: (template: string) => void;
  onClose: () => void;
}

// 定义各节点类型的默认输出字段
const getDefaultOutputFields = (nodeType: string): string[] => {
  switch (nodeType) {
    case "start":
      return ["inputs", "input"];
    case "llm":
      return ["output"];
    case "tool":
      return ["result", "output"];
    case "condition":
      return ["result", "conditionResult"];
    case "loop":
      return ["output", "iterations"];
    default:
      return ["output"];
  }
};

// 根据节点的输出格式和定义的字段返回对应的输出字段
// 返回格式：{ field: string, displayName: string, isNested: boolean }
const getNodeOutputFields = (
  node: Node,
): Array<{ field: string; displayName: string; isNested: boolean }> => {
  const nodeType = node.type || "start";
  const outputFormat =
    node.data?.outputFormat || node.data?.output_format || "array";
  const outputFields =
    node.data?.outputFields || node.data?.output_fields || [];

  const fields: Array<{
    field: string;
    displayName: string;
    isNested: boolean;
  }> = [];

  // 始终包含 output 字段（原始输出）
  fields.push({ field: "output", displayName: "output", isNested: false });

  // 如果定义了输出字段，添加这些字段（作为 output 的嵌套字段）
  if (Array.isArray(outputFields) && outputFields.length > 0) {
    outputFields.forEach((field: any) => {
      if (field?.name && typeof field.name === "string") {
        // 自定义字段应该通过 output.字段名 访问
        fields.push({
          field: `output.${field.name}`,
          displayName: field.name,
          isNested: true,
        });
      }
    });
  } else {
    // 如果没有定义字段，返回默认字段（针对特定节点类型）
    if (nodeType === "start") {
      fields.push({ field: "inputs", displayName: "inputs", isNested: false });
      fields.push({ field: "input", displayName: "input", isNested: false });
    } else if (nodeType === "tool") {
      fields.push({ field: "result", displayName: "result", isNested: false });
    } else if (nodeType === "condition") {
      fields.push({ field: "result", displayName: "result", isNested: false });
      fields.push({
        field: "conditionResult",
        displayName: "conditionResult",
        isNested: false,
      });
    } else if (nodeType === "loop") {
      fields.push({
        field: "iterations",
        displayName: "iterations",
        isNested: false,
      });
    }
  }

  return fields;
};

// 获取节点类型图标
const getNodeIcon = (nodeType: string) => {
  switch (nodeType) {
    case "start":
      return Play;
    case "llm":
      return Brain;
    case "tool":
      return Wrench;
    case "condition":
      return GitBranch;
    case "loop":
      return RotateCcw;
    default:
      return Play;
  }
};

export function UpstreamNodeSelector({
  currentNodeId,
  nodes,
  edges,
  onSelect,
  onClose,
}: UpstreamNodeSelectorProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [expandedLoopVars, setExpandedLoopVars] = useState(false);

  // 检查当前节点是否在循环体内
  const currentNode = useMemo(() => {
    return nodes.find((n) => n.id === currentNodeId);
  }, [currentNodeId, nodes]);

  const currentLoopId = currentNode?.data?.loopId || currentNode?.data?.loop_id;
  const isInLoop = !!currentLoopId;

  const directUpstreamIds = useMemo(
    () => getDirectUpstreamNodeIds(currentNodeId, edges),
    [currentNodeId, edges],
  );

  const { transitiveUpstream, loopExtraNodes } = useMemo(() => {
    if (!currentNode) {
      return { transitiveUpstream: [] as Node[], loopExtraNodes: [] as Node[] };
    }

    const ancestor = getTransitiveUpstreamNodes(currentNodeId, nodes, edges);
    const ancestorIds = new Set(ancestor.map((n) => n.id));
    const loopExtras: Node[] = [];

    if (isInLoop && currentLoopId) {
      const loopNode = nodes.find(
        (n) => n.id === currentLoopId && n.type === "loop",
      );
      if (loopNode) {
        const loopSourceNodeIds = edges
          .filter((edge) => edge.target === currentLoopId)
          .map((edge) => edge.source);
        for (const id of loopSourceNodeIds) {
          if (!ancestorIds.has(id)) {
            const n = nodes.find((x) => x.id === id);
            if (n) loopExtras.push(n);
          }
        }
        const loopBodyNodeIds = nodes.filter(
          (n) =>
            (n.data?.loopId === currentLoopId ||
              n.data?.loop_id === currentLoopId) &&
            n.id !== currentNodeId &&
            n.id !== currentLoopId &&
            !ancestorIds.has(n.id),
        );
        loopExtras.push(...loopBodyNodeIds);
      }
    }

    return { transitiveUpstream: ancestor, loopExtraNodes: loopExtras };
  }, [currentNode, currentNodeId, nodes, edges, isInLoop, currentLoopId]);

  const upstreamNodes = useMemo(() => {
    const seen = new Set<string>();
    const merged: Node[] = [];
    for (const n of [...transitiveUpstream, ...loopExtraNodes]) {
      if (seen.has(n.id)) continue;
      seen.add(n.id);
      merged.push(n);
    }
    return merged;
  }, [transitiveUpstream, loopExtraNodes]);

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const handleFieldSelect = (
    node: Node,
    fieldInfo: { field: string; displayName: string; isNested: boolean },
  ) => {
    const nodeIdentifier = getNodeIdentifier(node);
    // 确保 nodeIdentifier 是字符串
    const identifier =
      typeof nodeIdentifier === "string"
        ? nodeIdentifier
        : String(nodeIdentifier);
    const template = `{{${identifier}.${fieldInfo.field}}}`;
    onSelect(template);
    onClose();
  };

  const handleLoopVariableSelect = (variablePath: string) => {
    const template = `{{loop.variables.${variablePath}}}`;
    onSelect(template);
    onClose();
  };

  // 从 exit_node 获取输出字段，动态生成循环变量字段列表
  const loopVariableFields = useMemo(() => {
    if (!isInLoop || !currentLoopId) {
      return [];
    }

    // 找到循环体内的所有节点
    const loopBodyNodes = nodes.filter(
      (n) =>
        (n.data?.loopId === currentLoopId ||
          n.data?.loop_id === currentLoopId) &&
        n.id !== currentLoopId &&
        n.type !== "start" &&
        n.type !== "end",
    );

    // 找到 exit_node（循环体内没有下游连接的节点）
    const exitNodes = loopBodyNodes.filter((node) => {
      // 检查是否有下游连接（连接到循环体内的其他节点）
      const hasDownstream = edges.some(
        (edge) =>
          edge.source === node.id &&
          loopBodyNodes.some((n) => n.id === edge.target),
      );
      return !hasDownstream;
    });

    // 使用第一个 exit_node（如果有多个，优先使用第一个）
    const exitNode = exitNodes[0];
    if (!exitNode) {
      // 如果没有 exit_node，只返回基础字段
      return [
        { path: "pending_items", label: "pending_items" },
        { path: "iteration", label: "iteration" },
      ];
    }

    // 获取 exit_node 的输出字段
    const outputFields = getNodeOutputFields(exitNode);
    const outputFieldsConfig =
      exitNode.data?.outputFields || exitNode.data?.output_fields || [];

    // 构建字段列表
    const fields: Array<{ path: string; label: string }> = [];

    // 添加基础字段
    fields.push({ path: "pending_items", label: "pending_items" });
    fields.push({ path: "iteration", label: "iteration" });

    // 从 exit_node 的输出字段中提取字段名
    // 如果定义了 outputFields，使用定义的字段
    if (Array.isArray(outputFieldsConfig) && outputFieldsConfig.length > 0) {
      outputFieldsConfig.forEach((field: any) => {
        if (field?.name && typeof field.name === "string") {
          fields.push({
            path: `pending_items.${field.name}`,
            label: field.name,
          });
        }
      });
    } else {
      // 如果没有定义字段，尝试从 output 字段中推断
      // 这里只添加 output 字段，因为无法知道具体的嵌套字段结构
      if (outputFields.some((f) => f.field === "output")) {
        fields.push({
          path: "pending_items.output",
          label: "output",
        });
      }
    }

    return fields;
  }, [isInLoop, currentLoopId, nodes, edges]);

  if (upstreamNodes.length === 0 && !isInLoop) {
    return (
      <div className="w-80 p-4">
        <div className="text-muted-foreground py-8 text-center text-sm">
          没有上游节点
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-80 flex-col">
      <div className="border-border border-b p-3">
        <h3 className="text-sm font-semibold">选择变量</h3>
        <p className="text-muted-foreground mt-1 text-xs">
          可选链路上任意已执行祖先节点的 output 字段（不限直连）
        </p>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2">
          {/* 循环变量选项（如果当前节点在循环体内） */}
          {isInLoop && (
            <div className="border-border rounded-md border">
              <button
                onClick={() => setExpandedLoopVars(!expandedLoopVars)}
                className="hover:bg-accent flex w-full items-center gap-2 p-2 transition-colors"
              >
                {expandedLoopVars ? (
                  <ChevronDown className="text-muted-foreground h-4 w-4" />
                ) : (
                  <ChevronRight className="text-muted-foreground h-4 w-4" />
                )}
                <Database className="text-muted-foreground h-4 w-4" />
                <span className="flex-1 text-left text-sm font-medium">
                  循环变量
                </span>
              </button>
              {expandedLoopVars && (
                <div className="border-border bg-muted/30 border-t">
                  {loopVariableFields.map((field) => (
                    <button
                      key={field.path}
                      onClick={() => handleLoopVariableSelect(field.path)}
                      className="hover:bg-accent flex w-full items-center gap-2 px-6 py-2 text-left text-sm transition-colors"
                    >
                      <span className="text-muted-foreground">└─</span>
                      <span className="font-mono text-xs">{field.label}</span>
                      <span className="text-muted-foreground ml-auto text-xs">
                        {`{{loop.variables.${field.path}}}`}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 上游节点选项（含链路上更早的祖先节点） */}
          {upstreamNodes.map((node) => {
            const Icon = getNodeIcon(node.type || "start");
            const isExpanded = expandedNodes.has(node.id);
            const outputFields = getNodeOutputFields(node);
            const nodeLabel =
              typeof node.data?.displayName === "string"
                ? node.data.displayName
                : typeof node.data?.label === "string"
                  ? node.data.label
                  : String(node.id);
            const nodeIdentifier = getNodeIdentifier(node);
            const isDirect = directUpstreamIds.has(node.id);

            return (
              <div key={node.id} className="border-border rounded-md border">
                <button
                  onClick={() => toggleNode(node.id)}
                  className="hover:bg-accent flex w-full items-center gap-2 p-2 transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown className="text-muted-foreground h-4 w-4" />
                  ) : (
                    <ChevronRight className="text-muted-foreground h-4 w-4" />
                  )}
                  <Icon className="text-muted-foreground h-4 w-4" />
                  <span className="flex-1 text-left text-sm font-medium">
                    {nodeLabel}
                  </span>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px]",
                      isDirect
                        ? "bg-primary/10 text-primary"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {isDirect ? "直连" : "更早上游"}
                  </span>
                </button>
                {isExpanded && (
                  <div className="border-border bg-muted/30 border-t">
                    {outputFields.map((fieldInfo) => (
                      <button
                        key={fieldInfo.field}
                        onClick={() => handleFieldSelect(node, fieldInfo)}
                        className="hover:bg-accent flex w-full items-center gap-2 px-6 py-2 text-left text-sm transition-colors"
                      >
                        <span className="text-muted-foreground">└─</span>
                        <span className="font-mono text-xs">
                          {fieldInfo.displayName}
                        </span>
                        <span className="text-muted-foreground ml-auto text-xs">
                          {`{{${nodeIdentifier}.${fieldInfo.field}}}`}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}

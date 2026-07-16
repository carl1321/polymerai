// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import type { Edge } from "@xyflow/react";

import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";

interface EdgeConfigPanelProps {
  edge: Edge;
  onUpdate: (edgeId: string, data: any) => void;
  onClose: () => void;
}

export function EdgeConfigPanel({
  edge,
  onUpdate,
  onClose,
}: EdgeConfigPanelProps) {
  const condition = (edge.data as { condition?: string } | undefined)
    ?.condition;
  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">边配置</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
        <p className="text-muted-foreground mt-1 text-sm">
          从 {edge.source} 到 {edge.target}
        </p>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {condition && (
          <div>
            <Label>条件分支</Label>
            <Input value={condition} disabled />
            <p className="text-muted-foreground mt-1 text-xs">
              条件节点的分支标识
            </p>
          </div>
        )}
        {!condition && (
          <div className="text-muted-foreground py-8 text-center text-sm">
            此边无需额外配置
            <p className="mt-2 text-xs">
              参数映射已在节点配置中通过变量引用实现
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

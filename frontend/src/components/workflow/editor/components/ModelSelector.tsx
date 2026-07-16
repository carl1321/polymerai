// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Check, Loader2 } from "lucide-react";
import { useState, useMemo } from "react";

import { useModels } from "@/core/models/hooks";
import type { Model } from "@/core/models/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { cn } from "~/lib/utils";

interface ModelSelectorProps {
  value?: string;
  onChange: (modelName: string) => void;
  className?: string;
}

export function ModelSelector({
  value,
  onChange,
  className,
}: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const { models, isLoading } = useModels();

  // 获取所有可用模型
  const availableModels = useMemo(() => {
    return models ?? [];
  }, [models]);

  // 如果已有模型名称但不在列表中，保留它（向后兼容）
  const currentModel = availableModels.find((m) => m.name === value);
  const displayValue = currentModel
    ? `${currentModel.display_name || currentModel.name}`
    : value || "未选择模型";

  if (isLoading) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />
        <span className="text-muted-foreground text-sm">加载模型中...</span>
      </div>
    );
  }

  if (availableModels.length === 0) {
    return (
      <div className={cn("text-muted-foreground text-sm", className)}>
        没有可用模型
      </div>
    );
  }

  return (
    <Select
      value={value || ""}
      onValueChange={(newValue) => {
        onChange(newValue);
      }}
      open={open}
      onOpenChange={setOpen}
    >
      <SelectTrigger className={className}>
        <SelectValue placeholder="选择模型">{displayValue}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {availableModels.map((model) => (
          <SelectItem key={model.name} value={model.name}>
            <div className="flex items-center gap-2">
              {value === model.name && (
                <Check className="text-primary h-4 w-4" />
              )}
              <div className="flex flex-col">
                <span className="font-medium">
                  {model.display_name || model.name}
                </span>
                <span className="text-muted-foreground text-xs">
                  {model.name}
                </span>
              </div>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

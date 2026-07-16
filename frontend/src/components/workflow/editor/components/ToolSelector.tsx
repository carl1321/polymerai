// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Wrench, Search, Loader2 } from "lucide-react";
import { useState, useEffect, useCallback } from "react";

import { Button } from "~/components/ui/button";
import { Checkbox } from "~/components/ui/checkbox";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { ScrollArea } from "~/components/ui/scroll-area";
import { getAvailableTools, type ToolDefinition } from "~/core/api/workflow";
import { cn } from "~/lib/utils";

interface ToolSelectorProps {
  value?: string[];
  onChange: (tools: string[]) => void;
}

export function ToolSelector({ value = [], onChange }: ToolSelectorProps) {
  // 确保 value 始终是数组，防止 null 或 undefined
  const safeValue = Array.isArray(value) ? value : [];

  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = useCallback(async () => {
    try {
      setLoading(true);
      const availableTools = await getAvailableTools();
      setTools(availableTools);
    } catch (error) {
      console.error("Failed to load tools:", error);
      setTools([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const filteredTools = tools.filter(
    (tool) =>
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (tool.description ?? "")
        .toLowerCase()
        .includes(searchQuery.toLowerCase()),
  );

  const handleToolToggle = (toolName: string, checked: boolean) => {
    if (checked) {
      onChange([...safeValue, toolName]);
    } else {
      onChange(safeValue.filter((name) => name !== toolName));
    }
  };

  return (
    <div className="space-y-2">
      <Label className="text-foreground">工具</Label>
      <div className="space-y-2">
        {/* 搜索框 */}
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="搜索工具..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* 工具列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
          </div>
        ) : filteredTools.length === 0 ? (
          <div className="text-muted-foreground py-8 text-center text-sm">
            {searchQuery ? "没有找到匹配的工具" : "没有可用工具"}
          </div>
        ) : (
          <ScrollArea className="border-border h-[200px] rounded-md border p-2">
            <div className="space-y-2">
              {filteredTools.map((tool) => {
                const isSelected = safeValue.includes(tool.name);
                return (
                  <label
                    key={tool.name}
                    className={cn(
                      "hover:bg-accent flex cursor-pointer items-start gap-3 rounded-md p-2 transition-colors",
                      isSelected && "bg-accent",
                    )}
                  >
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={(checked) =>
                        handleToolToggle(tool.name, checked === true)
                      }
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Wrench className="text-muted-foreground h-4 w-4 shrink-0" />
                        <span className="text-foreground text-sm font-medium">
                          {tool.name}
                        </span>
                      </div>
                      {tool.description && (
                        <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                          {tool.description}
                        </p>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          </ScrollArea>
        )}

        {/* 已选工具显示 */}
        {safeValue.length > 0 && (
          <div className="border-border border-t pt-2">
            <p className="text-muted-foreground mb-2 text-xs">
              已选择 {safeValue.length} 个工具
            </p>
            <div className="flex flex-wrap gap-1">
              {safeValue.map((toolName) => {
                const tool = tools.find((t) => t.name === toolName);
                return (
                  <span
                    key={toolName}
                    className="bg-primary/10 text-primary inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs"
                  >
                    {tool?.name || toolName}
                    <button
                      onClick={() => handleToolToggle(toolName, false)}
                      className="hover:bg-primary/20 rounded-full p-0.5"
                      aria-label={`移除 ${toolName}`}
                    >
                      ×
                    </button>
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

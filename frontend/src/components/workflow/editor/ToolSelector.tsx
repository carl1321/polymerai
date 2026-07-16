// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Search } from "lucide-react";
import { useEffect, useState, useMemo } from "react";

import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { getAvailableTools } from "~/core/api/workflow";

interface ToolDefinition {
  name: string;
  description: string;
  parameters: Array<{
    name: string;
    type: string;
    description?: string;
    required?: boolean;
  }>;
}

interface ToolSelectorProps {
  selectedTool?: string;
  onSelect: (toolName: string) => void;
  onClose: () => void;
}

export function ToolSelector({
  selectedTool,
  onSelect,
  onClose,
}: ToolSelectorProps) {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      setLoading(true);
      const toolsData = await getAvailableTools();
      setTools(toolsData);
    } catch (error) {
      console.error("Error loading tools:", error);
    } finally {
      setLoading(false);
    }
  };

  const filteredTools = useMemo(() => {
    if (!searchQuery) return tools;
    const query = searchQuery.toLowerCase();
    return tools.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        (tool.description ?? "").toLowerCase().includes(query),
    );
  }, [tools, searchQuery]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-4">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-semibold">选择工具</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="搜索工具..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-muted-foreground py-8 text-center text-sm">
            加载中...
          </div>
        ) : filteredTools.length === 0 ? (
          <div className="text-muted-foreground py-8 text-center text-sm">
            {searchQuery ? "未找到匹配的工具" : "暂无可用工具"}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredTools.map((tool) => (
              <button
                key={tool.name}
                onClick={() => {
                  onSelect(tool.name);
                  onClose();
                }}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  selectedTool === tool.name
                    ? "border-primary bg-primary/10"
                    : "border-border hover:bg-accent"
                }`}
              >
                <div className="text-sm font-medium">{tool.name}</div>
                <div className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                  {tool.description}
                </div>
                {(tool.parameters?.length ?? 0) > 0 && (
                  <div className="text-muted-foreground mt-2 text-xs">
                    {tool.parameters.length} 个参数
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

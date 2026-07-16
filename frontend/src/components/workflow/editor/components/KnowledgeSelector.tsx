// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { BookOpen, X, Search, Loader2 } from "lucide-react";
import { useState, useEffect, useCallback } from "react";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "~/components/ui/popover";
import { queryRAGResources } from "~/core/api/rag";
import type { Resource } from "~/core/messages";
import { cn } from "~/lib/utils";

interface KnowledgeSelectorItem {
  uri: string;
  title?: string;
  description?: string;
}

interface KnowledgeSelectorProps {
  value?: KnowledgeSelectorItem[];
  onChange: (resources: KnowledgeSelectorItem[]) => void;
}

export function KnowledgeSelector({
  value = [],
  onChange,
}: KnowledgeSelectorProps) {
  // 确保 value 始终是一个数组，防止 null 或 undefined
  const safeValue: KnowledgeSelectorItem[] = Array.isArray(value) ? value : [];

  const [open, setOpen] = useState(false);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const loadResources = useCallback(async (query = "") => {
    try {
      setLoading(true);
      const results = await queryRAGResources(query);
      setResources(results);
    } catch (error) {
      console.error("Failed to load resources:", error);
      setResources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadResources(searchQuery);
    }
  }, [open, searchQuery, loadResources]);

  const handleSelectResource = (resource: Resource) => {
    const isSelected = safeValue.some((r) => r.uri === resource.uri);
    if (isSelected) {
      onChange(safeValue.filter((r) => r.uri !== resource.uri));
    } else {
      onChange([
        ...safeValue,
        {
          uri: resource.uri,
          // 后端 Resource.title/description 可能为 undefined，这里兜底为字符串以便展示。
          title: resource.title ?? resource.uri,
          description: resource.description ?? "",
        },
      ]);
    }
  };

  const handleRemoveResource = (uri: string) => {
    onChange(safeValue.filter((r) => r.uri !== uri));
  };

  const isResourceSelected = (uri: string) => {
    return safeValue.some((r) => r.uri === uri);
  };

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full justify-start"
          >
            <BookOpen className="mr-2 h-4 w-4" />
            选择知识库
            {safeValue.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {safeValue.length}
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-96 p-0" align="start">
          <div className="border-border border-b p-3">
            <div className="relative">
              <Search className="text-muted-foreground absolute top-1/2 left-2 h-4 w-4 -translate-y-1/2" />
              <Input
                type="text"
                placeholder="搜索知识库..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto p-2">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
              </div>
            ) : resources.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                {searchQuery ? "未找到匹配的资源" : "暂无知识库资源"}
              </div>
            ) : (
              <div className="space-y-1">
                {resources.map((resource) => {
                  const selected = isResourceSelected(resource.uri);
                  return (
                    <button
                      key={resource.uri}
                      onClick={() => handleSelectResource(resource)}
                      className={cn(
                        "w-full rounded-lg border p-3 text-left transition-colors",
                        selected
                          ? "border-primary bg-primary/5"
                          : "border-border hover:bg-accent",
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <BookOpen
                          className={cn(
                            "mt-0.5 h-4 w-4 flex-shrink-0",
                            selected ? "text-primary" : "text-muted-foreground",
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-foreground text-sm font-medium">
                            {resource.title}
                          </div>
                          {resource.description && (
                            <div className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                              {resource.description}
                            </div>
                          )}
                          <div className="text-muted-foreground mt-1 truncate font-mono text-xs">
                            {resource.uri.replace("rag://dataset/", "")}
                          </div>
                        </div>
                        {selected && (
                          <div className="text-primary flex-shrink-0">✓</div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>

      {/* 已选择的知识库列表 */}
      {safeValue.length > 0 && (
        <div className="space-y-1">
          {safeValue.map((resource) => (
            <div
              key={resource.uri}
              className="border-border bg-muted/50 flex items-center justify-between rounded-lg border p-2"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <BookOpen className="text-muted-foreground h-3 w-3 flex-shrink-0" />
                <span className="text-foreground truncate text-sm">
                  {resource.title}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 flex-shrink-0"
                onClick={() => handleRemoveResource(resource.uri)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

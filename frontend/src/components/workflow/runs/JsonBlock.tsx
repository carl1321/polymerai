// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { Copy, Check } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { formatJson, isEmptyValue } from "./run-display-utils";

type JsonBlockProps = {
  label: string;
  value: unknown;
  emptyHint?: string;
  maxHeightClass?: string;
};

export function JsonBlock({
  label,
  value,
  emptyHint = "（无数据）",
  maxHeightClass = "max-h-[280px]",
}: JsonBlockProps) {
  const [copied, setCopied] = useState(false);
  const text = isEmptyValue(value) ? "" : formatJson(value);

  const handleCopy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-xs font-medium">
          {label}
        </span>
        {text ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => void handleCopy()}
          >
            {copied ? (
              <Check className="h-3 w-3" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
            <span className="ml-1 text-xs">{copied ? "已复制" : "复制"}</span>
          </Button>
        ) : null}
      </div>
      <div
        className={`bg-muted/40 overflow-auto rounded-md border p-2 ${maxHeightClass}`}
      >
        <pre className="font-mono text-xs break-all whitespace-pre-wrap">
          {text || emptyHint}
        </pre>
      </div>
    </div>
  );
}

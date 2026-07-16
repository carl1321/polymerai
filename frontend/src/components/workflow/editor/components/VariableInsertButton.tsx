// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import type { Node, Edge } from "@xyflow/react";
import { Variable } from "lucide-react";
import { useRef, useState, useCallback } from "react";

import { Button } from "~/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "~/components/ui/popover";

import { UpstreamNodeSelector } from "./UpstreamNodeSelector";

interface VariableInsertButtonProps {
  currentNodeId: string;
  nodes: Node[];
  edges: Edge[];
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function VariableInsertButton({
  currentNodeId,
  nodes,
  edges,
  textareaRef,
  inputRef,
  value,
  onChange,
  className,
}: VariableInsertButtonProps) {
  const [open, setOpen] = useState(false);

  const insertAtCursor = useCallback(
    (text: string) => {
      const field = textareaRef?.current ?? inputRef?.current;
      if (!field) return;

      const start = field.selectionStart ?? value.length;
      const end = field.selectionEnd ?? value.length;
      const currentValue = value;

      const newValue =
        currentValue.substring(0, start) + text + currentValue.substring(end);

      onChange(newValue);

      setTimeout(() => {
        const newCursorPos = start + text.length;
        field.setSelectionRange(newCursorPos, newCursorPos);
        field.focus();
      }, 0);
    },
    [textareaRef, inputRef, value, onChange],
  );

  const handleSelect = useCallback(
    (template: string) => {
      insertAtCursor(template);
      setOpen(false);
    },
    [insertAtCursor],
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className={className}>
          <Variable className="mr-2 h-4 w-4" />
          插入变量
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-auto p-0"
        align="start"
        side="bottom"
        sideOffset={4}
      >
        <UpstreamNodeSelector
          currentNodeId={currentNodeId}
          nodes={nodes}
          edges={edges}
          onSelect={handleSelect}
          onClose={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}

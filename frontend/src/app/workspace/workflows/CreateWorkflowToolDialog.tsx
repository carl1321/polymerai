"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const SLUG_RE = /^[a-z][a-z0-9_]{1,63}$/;

interface CreateWorkflowToolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (payload: {
    name: string;
    display_name: string;
    description?: string;
  }) => void | Promise<void>;
}

export function CreateWorkflowToolDialog({
  open,
  onOpenChange,
  onCreate,
}: CreateWorkflowToolDialogProps) {
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setName("");
    setDisplayName("");
    setDescription("");
    setError("");
  };

  const handleSubmit = async () => {
    const slug = name.trim();
    const label = displayName.trim() || slug;
    if (!slug) {
      setError("工具标识是必填项");
      return;
    }
    if (!SLUG_RE.test(slug)) {
      setError("标识须为小写字母开头，仅含字母、数字、下划线（2–64 位）");
      return;
    }

    setSubmitting(true);
    try {
      await onCreate({
        name: slug,
        display_name: label,
        description: description.trim() || undefined,
      });
      reset();
      onOpenChange(false);
    } catch {
      // caller shows toast
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = () => {
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建工具</DialogTitle>
          <DialogDescription>
            创建后可在工具库中编写 @tool 脚本、试跑并发布，供工作流 Tool
            节点选用。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="tool-slug">
              工具标识 <span className="text-red-500">*</span>
            </Label>
            <Input
              id="tool-slug"
              value={name}
              onChange={(e) => {
                setName(
                  e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""),
                );
                setError("");
              }}
              placeholder="例如 my_workflow_tool"
              className={error ? "border-red-500" : ""}
            />
            <p className="text-muted-foreground text-xs">
              须与脚本中 @tool 函数名一致
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="tool-display-name">显示名称</Label>
            <Input
              id="tool-display-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="在列表中展示的名称"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tool-description">描述</Label>
            <Textarea
              id="tool-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="工具用途说明（可选）"
              rows={3}
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={submitting}
          >
            取消
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="bg-[#1890FF] text-white hover:bg-[#1890FF]/90"
          >
            {submitting ? "创建中…" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

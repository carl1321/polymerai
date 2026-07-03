// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Textarea } from "~/components/ui/textarea";
import { toast } from "sonner";
import { Upload } from "lucide-react";

export type StartInputFieldDef = {
  key: string;
  label: string;
  type: "string" | "path" | "number";
  required?: boolean;
  default?: string;
};

export type StartFilesDef = {
  accept?: string;
  maxCount?: number;
};

type WorkflowRunDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  startInputInfo?: string;
  startInputs?: StartInputFieldDef[];
  startFiles?: StartFilesDef;
  allowFileUpload?: boolean;
  submitting?: boolean;
  onSubmit: (payload: {
    values: Record<string, string | number>;
    files: File[];
    fileFieldKeys: string[];
  }) => void | Promise<void>;
};

export function WorkflowRunDialog({
  open,
  onOpenChange,
  startInputInfo,
  startInputs = [],
  startFiles,
  allowFileUpload = true,
  submitting,
  onSubmit,
}: WorkflowRunDialogProps) {
  const fields = useMemo(() => startInputs.filter((f) => f.key?.trim()), [startInputs]);
  const pathFieldDefs = useMemo(
    () => fields.filter((f) => f.type === "path"),
    [fields],
  );
  const pathKeys = useMemo(() => pathFieldDefs.map((f) => f.key), [pathFieldDefs]);

  const [values, setValues] = useState<Record<string, string>>({});
  const [filesByKey, setFilesByKey] = useState<Record<string, File | null>>({});
  const [genericFiles, setGenericFiles] = useState<File[]>([]);

  const showFileUpload = allowFileUpload;
  const usePerFieldUpload = pathKeys.length > 0;

  useEffect(() => {
    if (!open) return;
    const init: Record<string, string> = { input: "" };
    for (const f of fields) {
      init[f.key] = f.default ?? "";
    }
    setValues(init);
    setFilesByKey({});
    setGenericFiles([]);
  }, [open, fields]);

  const handleGenericFiles = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const list = e.target.files;
      if (!list) return;
      const max = startFiles?.maxCount ?? 5;
      setGenericFiles(Array.from(list).slice(0, max));
    },
    [startFiles?.maxCount],
  );

  const handleSubmit = async () => {
    for (const f of fields) {
      if (f.required && f.type !== "path" && !String(values[f.key] ?? "").trim()) {
        toast.error(`请填写：${f.label || f.key}`);
        return;
      }
    }
    if (usePerFieldUpload) {
      for (const f of pathFieldDefs) {
        if (f.required && !filesByKey[f.key]) {
          toast.error(`请上传：${f.label || f.key}`);
          return;
        }
      }
    }

    const numeric: Record<string, string | number> = {};
    for (const f of fields) {
      if (f.type === "path") continue;
      const raw = values[f.key] ?? "";
      if (f.type === "number") {
        const n = Number(raw);
        numeric[f.key] = Number.isFinite(n) ? n : raw;
      } else {
        numeric[f.key] = raw;
      }
    }
    const runNote = String(values.input ?? "").trim();
    if (runNote) {
      numeric.input = runNote;
    }

    let files: File[] = [];
    let fileFieldKeys: string[] = [];
    if (usePerFieldUpload) {
      for (const key of pathKeys) {
        const file = filesByKey[key];
        if (file) {
          files.push(file);
          fileFieldKeys.push(key);
        }
      }
    } else if (showFileUpload && genericFiles.length > 0) {
      files = genericFiles;
      fileFieldKeys = ["poscar_path"];
    }

    if (showFileUpload && pathFieldDefs.some((f) => f.required) && files.length === 0) {
      toast.error("请上传所需附件");
      return;
    }

    const nonPathFields = fields.filter((f) => f.type !== "path");
    const hasText =
      nonPathFields.some((f) => String(values[f.key] ?? "").trim()) ||
      String(values.input ?? "").trim();
    const hasFile =
      showFileUpload &&
      (usePerFieldUpload
        ? pathKeys.some((k) => filesByKey[k])
        : genericFiles.length > 0);
    const canProvideText = true;
    const canProvideFile = showFileUpload;
    if ((canProvideText || canProvideFile) && !hasText && !hasFile) {
      toast.error("请填写运行参数或上传至少一个附件");
      return;
    }

    await onSubmit({ values: numeric, files, fileFieldKeys });
  };

  const acceptHint = startFiles?.accept ?? ".vasp,.cif,.poscar,.POSCAR,.CONTCAR";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>运行工作流</DialogTitle>
          <DialogDescription>
            {startInputInfo?.trim() || "填写参数并上传附件后执行。"}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label htmlFor="run-input-note">运行说明</Label>
            <Textarea
              id="run-input-note"
              placeholder="可输入文字说明（与上传附件二选一或同时填写）"
              value={values.input ?? ""}
              onChange={(e) =>
                setValues((prev) => ({ ...prev, input: e.target.value }))
              }
              rows={3}
              className="mt-1"
            />
          </div>

          {fields
            .filter((f) => f.type !== "path" || !usePerFieldUpload)
            .map((f) => (
              <div key={f.key}>
                <Label htmlFor={`run-${f.key}`}>
                  {f.label || f.key}
                  {f.required ? " *" : ""}
                </Label>
                {f.type === "path" ? (
                  <p className="text-xs text-muted-foreground mt-1">请在下方附件区选择文件。</p>
                ) : (
                  <Input
                    id={`run-${f.key}`}
                    type={f.type === "number" ? "number" : "text"}
                    value={values[f.key] ?? ""}
                    onChange={(e) =>
                      setValues((prev) => ({ ...prev, [f.key]: e.target.value }))
                    }
                    placeholder={f.default}
                    className="mt-1"
                  />
                )}
              </div>
            ))}

          {showFileUpload && usePerFieldUpload && (
            <div className="space-y-3 rounded-md border bg-muted/20 p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Upload className="h-4 w-4" />
                上传附件
              </div>
              {pathFieldDefs.map((f) => (
                <div key={f.key}>
                  <Label htmlFor={`file-${f.key}`}>
                    {f.label || f.key}
                    {f.required ? " *" : ""}
                  </Label>
                  <Input
                    id={`file-${f.key}`}
                    type="file"
                    accept={acceptHint}
                    className="mt-1"
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null;
                      setFilesByKey((prev) => ({ ...prev, [f.key]: file }));
                    }}
                  />
                  {filesByKey[f.key] ? (
                    <p className="text-xs text-muted-foreground mt-1">
                      已选：{filesByKey[f.key]!.name}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}

          {showFileUpload && !usePerFieldUpload && (
            <div className="space-y-2 rounded-md border bg-muted/20 p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Upload className="h-4 w-4" />
                上传附件
              </div>
              <p className="text-xs text-muted-foreground">
                支持 POSCAR、CONTCAR、.vasp 等；将保存到 inputs/ 并写入 poscar_path（若未单独配置字段）。
              </p>
              <Input
                type="file"
                multiple={(startFiles?.maxCount ?? 5) > 1}
                accept={acceptHint}
                onChange={handleGenericFiles}
              />
              {genericFiles.length > 0 && (
                <ul className="text-xs text-muted-foreground list-disc pl-4">
                  {genericFiles.map((f) => (
                    <li key={f.name}>{f.name}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting}>
            {submitting ? "提交中…" : "开始运行"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

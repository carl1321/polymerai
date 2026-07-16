"use client";

import {
  CheckCircle2,
  Download,
  FileUp,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkflowToolCodeEditor } from "@/components/workflow-tools/WorkflowToolCodeEditor";
import {
  createWorkflowTool,
  deleteWorkflowTool,
  getWorkflowTool,
  importSystemWorkflowTools,
  listScriptWorkflowTools,
  publishWorkflowTool,
  setWorkflowToolEnabled,
  downloadWorkflowToolTestFile,
  testWorkflowTool,
  updateWorkflowTool,
  uploadWorkflowToolTestFile,
  type WorkflowToolItem,
  type WorkflowToolOutputFile,
} from "@/core/api/workflow-tools";
import { useIsAppAdmin } from "@/hooks/use-is-app-admin";
import { parsePythonErrorLine } from "@/lib/parse-python-error-line";

import { CreateWorkflowToolDialog } from "../workflows/CreateWorkflowToolDialog";

type TestParamRow = { id: string; name: string; value: string };

function newTestParamRow(name = "", value = ""): TestParamRow {
  return { id: crypto.randomUUID(), name, value };
}

function rowsToInvokeParams(rows: TestParamRow[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    const key = row.name.trim();
    if (!key) continue;
    out[key] = row.value;
  }
  return out;
}

function defaultTestParamRows(
  prev: TestParamRow[],
  keepValues: boolean,
): TestParamRow[] {
  if (keepValues && prev.length > 0) return prev;
  return [newTestParamRow("query", "")];
}

function isFileParam(name: string, type?: string): boolean {
  if (type === "file") return true;
  return (
    /_(path|file|filepath)$/i.test(name) ||
    /^(path|file|input_file|input_path|output_file|output_path)$/i.test(name) ||
    /^output(_file|_path)?$/i.test(name)
  );
}

function defaultTestParamValue(name: string): string {
  if (/^output(_file|_path)?$/i.test(name) || name === "out_file") {
    return "outputs/result.out";
  }
  return "";
}

function formatTestOutput(output: unknown): string {
  if (output === undefined || output === null) return "(空)";
  if (typeof output === "string") return output;
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

export default function WorkflowToolsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isAdmin = useIsAppAdmin();
  const toolIdFromUrl = searchParams.get("toolId");
  const actionCreate = searchParams.get("action") === "create";
  const [tools, setTools] = useState<WorkflowToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(toolIdFromUrl);
  const [detailMeta, setDetailMeta] = useState<WorkflowToolItem | null>(null);
  const [script, setScript] = useState("");
  const [testParamRows, setTestParamRows] = useState<TestParamRow[]>([]);
  const [errorLine, setErrorLine] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{
    success?: boolean;
    output?: unknown;
    error?: string;
    logs?: string;
    depsError?: boolean;
    outputFiles?: WorkflowToolOutputFile[];
  } | null>(null);
  const [uploadingField, setUploadingField] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const selected =
    tools.find((t) => t.id === selectedId) ??
    (detailMeta?.id === selectedId ? detailMeta : null);

  const loadTools = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listScriptWorkflowTools();
      setTools(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTools();
  }, [loadTools]);

  useEffect(() => {
    if (toolIdFromUrl) setSelectedId(toolIdFromUrl);
  }, [toolIdFromUrl]);

  useEffect(() => {
    if (actionCreate && isAdmin) setCreateOpen(true);
  }, [actionCreate, isAdmin]);

  const loadDetail = useCallback(
    async (id: string, opts?: { keepTestOutput?: boolean }) => {
      try {
        const detail = await getWorkflowTool(id);
        setDetailMeta(detail);
        if (!opts?.keepTestOutput) {
          setScript(detail.script ?? "");
          setTestResult(null);
          setErrorLine(null);
        }
        setTestParamRows((prev) =>
          defaultTestParamRows(prev, Boolean(opts?.keepTestOutput)),
        );
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "加载工具详情失败");
      }
    },
    [],
  );

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const handleSave = async () => {
    if (!selectedId || selected?.source !== "script") return;
    setSaving(true);
    try {
      await updateWorkflowTool(selectedId, { script });
      toast.success("已保存");
      await loadTools();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!selectedId) return;
    setTesting(true);
    setTestResult(null);
    setErrorLine(null);
    try {
      await updateWorkflowTool(selectedId, { script });
      const params = rowsToInvokeParams(testParamRows);
      const res = await testWorkflowTool(selectedId, params);
      const logsText = res.logs ?? res.error ?? "";
      const line =
        res.errorLine ??
        parsePythonErrorLine(logsText) ??
        parsePythonErrorLine(res.error ?? "");
      setTestResult({
        success: res.success,
        output: res.output,
        error: res.error,
        logs: res.logs,
        depsError: res.depsError,
        outputFiles: res.outputFiles,
      });
      if (res.success) {
        setErrorLine(null);
        toast.success("试跑通过");
        await loadTools();
        if (selectedId) await loadDetail(selectedId, { keepTestOutput: true });
      } else {
        setErrorLine(line);
        toast.error(
          line != null
            ? `试跑失败（第 ${line} 行）`
            : res.depsMessage || res.error || "试跑失败",
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "试跑失败";
      const line = parsePythonErrorLine(msg);
      setErrorLine(line);
      setTestResult({ success: false, error: msg });
      toast.error(line != null ? `试跑失败（第 ${line} 行）` : msg);
    } finally {
      setTesting(false);
    }
  };

  const handleDelete = async (tool: WorkflowToolItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (
      !confirm(
        `确定删除工具「${tool.displayName || tool.name}」吗？此操作不可恢复。`,
      )
    )
      return;
    try {
      await deleteWorkflowTool(tool.id);
      toast.success("已删除");
      if (selectedId === tool.id) {
        setSelectedId(null);
        setDetailMeta(null);
        setTestResult(null);
        setErrorLine(null);
        router.replace("/workspace/workflow-tools");
      }
      await loadTools();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  const handleUploadTestFile = async (file: File, field?: string) => {
    if (!selectedId) return;
    setUploadingField(field ?? "__general__");
    try {
      const res = await uploadWorkflowToolTestFile(selectedId, file, field);
      const rel = res.file.relativePath;
      if (field) {
        setTestParamRows((prev) =>
          prev.map((r) => (r.name.trim() === field ? { ...r, value: rel } : r)),
        );
      }
      toast.success(`已上传：${res.file.filename}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploadingField(null);
    }
  };

  const handlePublish = async () => {
    if (!selectedId) return;
    try {
      await publishWorkflowTool(selectedId);
      toast.success("已发布");
      await loadTools();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "发布失败");
    }
  };

  const handleImportSystem = async () => {
    try {
      const res = await importSystemWorkflowTools();
      toast.success(`已导入 ${res.imported} 个系统工具`);
      await loadTools();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "导入失败");
    }
  };

  const toggleEnabled = async (tool: WorkflowToolItem) => {
    try {
      await setWorkflowToolEnabled(tool.id, !tool.enabled);
      await loadTools();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "更新失败");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#F5F5F5] dark:bg-slate-900">
      <div className="shrink-0 px-6 py-4">
        <div
          className="overflow-hidden rounded-xl bg-gradient-to-br from-[#0f172a] via-[#1e3a5f] to-[#0f172a] p-6 text-white shadow-lg dark:from-slate-900 dark:via-blue-950/50 dark:to-slate-900"
          style={{ minHeight: "100px" }}
        >
          <h2 className="mb-2 text-xl font-bold">工作流工具库</h2>
          <p className="max-w-2xl text-sm text-white/90">
            管理你创建的自定义工具（@tool 脚本）；试跑并发布后在 Tool
            节点选用。系统内置工具不在此列表展示。
            <Link
              href="/workspace/workflows"
              className="ml-2 text-white underline"
            >
              返回工作流
            </Link>
          </p>
        </div>
      </div>

      <div className="shrink-0 px-6 py-2">
        <div className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          操作
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadTools()}
            className="rounded-lg border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            刷新
          </Button>
          {isAdmin && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleImportSystem()}
                className="rounded-lg border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
              >
                <Upload className="mr-1.5 h-4 w-4" />
                导入系统工具
              </Button>
              <Button
                size="sm"
                onClick={() => setCreateOpen(true)}
                className="rounded-lg bg-[#1890FF] text-white hover:bg-[#1890FF]/90"
              >
                <Plus className="mr-1.5 h-4 w-4" />
                新建工具
              </Button>
            </>
          )}
        </div>
      </div>

      {isAdmin && (
        <CreateWorkflowToolDialog
          open={createOpen}
          onOpenChange={(open) => {
            setCreateOpen(open);
            if (!open && actionCreate) {
              router.replace(
                toolIdFromUrl
                  ? `/workspace/workflow-tools?toolId=${encodeURIComponent(toolIdFromUrl)}`
                  : "/workspace/workflow-tools",
              );
            }
          }}
          onCreate={async ({ name, display_name, description }) => {
            const created = await createWorkflowTool({
              name,
              display_name,
              description,
            });
            await loadTools();
            setSelectedId(created.id);
            await loadDetail(created.id);
            router.replace(`/workspace/workflow-tools?toolId=${created.id}`);
            toast.success("已创建工具，请编辑脚本并试跑");
          }}
        />
      )}

      <div className="flex min-h-0 flex-1">
        <ScrollArea className="w-72 border-r">
          <div className="space-y-1 p-2">
            {loading ? (
              <p className="text-muted-foreground p-4 text-sm">加载中…</p>
            ) : tools.length === 0 ? (
              <p className="text-muted-foreground p-4 text-sm">暂无工具</p>
            ) : (
              tools.map((tool) => (
                <div
                  key={tool.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedId(tool.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedId(tool.id);
                    }
                  }}
                  className={`flex w-full cursor-pointer items-start gap-1 rounded-md border px-3 py-2 text-left text-sm ${
                    selectedId === tool.id
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted border-transparent"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">
                      {tool.displayName || tool.name}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <Badge
                        variant={
                          tool.status === "published" ? "default" : "secondary"
                        }
                        className="text-[10px]"
                      >
                        {tool.status === "published" ? "已发布" : "草稿"}
                      </Badge>
                      {tool.source === "script" && tool.lastTestOk && (
                        <CheckCircle2 className="h-3 w-3 text-green-600" />
                      )}
                    </div>
                  </div>
                  {isAdmin && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                      onClick={(e) => void handleDelete(tool, e)}
                      aria-label="删除工具"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))
            )}
          </div>
        </ScrollArea>

        <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-auto p-4">
          {!selected ? (
            <p className="text-muted-foreground text-sm">
              {toolIdFromUrl && loading
                ? "正在加载工具…"
                : "请选择左侧工具，或点击「新建工具」"}
            </p>
          ) : selected.source === "script" ? (
            <>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <h2 className="font-semibold">
                  {selected.displayName || selected.name}
                </h2>
                <code className="bg-muted rounded border px-2 py-0.5 text-xs">
                  {selected.name}
                </code>
                {isAdmin && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={saving}
                      onClick={() => void handleSave()}
                    >
                      {saving ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        "保存"
                      )}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => void handlePublish()}
                      disabled={!selected.lastTestOk}
                    >
                      发布
                    </Button>
                  </>
                )}
              </div>

              <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
                <div className="flex min-h-[360px] min-w-0 flex-col gap-3">
                  <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm ring-1 ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:ring-slate-800">
                    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/90">
                      <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                        tool.py · LangChain @tool
                      </span>
                      <span className="text-[10px] text-slate-400">
                        Python · @tool 需含
                        &quot;&quot;&quot;说明&quot;&quot;&quot;
                      </span>
                    </div>
                    <WorkflowToolCodeEditor
                      value={script}
                      onChange={(v) => {
                        setScript(v);
                        setErrorLine(null);
                      }}
                      readOnly={!isAdmin}
                      errorLine={errorLine}
                      className="flex-1 rounded-none border-0"
                    />
                  </div>
                </div>

                <div className="flex h-full min-h-0 flex-col gap-2 lg:max-h-[calc(100vh-220px)]">
                  <div className="shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-950">
                    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-900/90">
                      <Label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                        Input
                      </Label>
                      {isAdmin && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-600 hover:text-[#1890FF]"
                          onClick={() =>
                            setTestParamRows((prev) => [
                              ...prev,
                              newTestParamRow(),
                            ])
                          }
                          aria-label="添加参数"
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                    <div className="max-h-[280px] space-y-2 overflow-y-auto p-2">
                      {testParamRows.length === 0 ? (
                        <p className="px-1 py-2 text-xs text-slate-400">
                          点击右上角 + 添加试跑参数
                        </p>
                      ) : (
                        testParamRows.map((row) => {
                          const key = row.name.trim();
                          const paramDef = (
                            selected?.parameters ??
                            detailMeta?.parameters ??
                            []
                          ).find((p) => p.name === key);
                          const showFile = key
                            ? isFileParam(key, paramDef?.type)
                            : false;
                          const uploadKey = key || row.id;
                          return (
                            <div
                              key={row.id}
                              className="flex items-center gap-1"
                            >
                              <Input
                                value={row.name}
                                onChange={(e) =>
                                  setTestParamRows((prev) =>
                                    prev.map((r) =>
                                      r.id === row.id
                                        ? { ...r, name: e.target.value }
                                        : r,
                                    ),
                                  )
                                }
                                readOnly={!isAdmin}
                                placeholder="变量名"
                                aria-label="变量名"
                                className="h-8 w-[88px] shrink-0 bg-slate-50 font-mono text-sm text-xs dark:bg-slate-900"
                              />
                              <Input
                                value={row.value}
                                onChange={(e) =>
                                  setTestParamRows((prev) =>
                                    prev.map((r) =>
                                      r.id === row.id
                                        ? { ...r, value: e.target.value }
                                        : r,
                                    ),
                                  )
                                }
                                readOnly={!isAdmin}
                                placeholder={
                                  showFile
                                    ? /^output/i.test(key)
                                      ? "默认 outputs/result.out"
                                      : "值或 inputs/文件名"
                                    : "值"
                                }
                                aria-label={key ? `${key} 的值` : "参数值"}
                                className="h-8 min-w-0 flex-1 bg-slate-50 text-sm dark:bg-slate-900"
                              />
                              {isAdmin && showFile && key && (
                                <label
                                  className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800 ${
                                    uploadingField === uploadKey
                                      ? "pointer-events-none opacity-50"
                                      : "cursor-pointer"
                                  }`}
                                >
                                  <input
                                    type="file"
                                    className="sr-only"
                                    disabled={uploadingField === uploadKey}
                                    onChange={(e) => {
                                      const f = e.target.files?.[0];
                                      if (f) void handleUploadTestFile(f, key);
                                      e.target.value = "";
                                    }}
                                  />
                                  {uploadingField === uploadKey ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <FileUp className="h-3.5 w-3.5 text-slate-600" />
                                  )}
                                </label>
                              )}
                              {isAdmin && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 shrink-0 text-slate-400 hover:text-red-600"
                                  onClick={() =>
                                    setTestParamRows((prev) =>
                                      prev.filter((r) => r.id !== row.id),
                                    )
                                  }
                                  aria-label="删除参数"
                                >
                                  <X className="h-3.5 w-3.5" />
                                </Button>
                              )}
                            </div>
                          );
                        })
                      )}
                      {isAdmin && selectedId && (
                        <label className="flex cursor-pointer items-center gap-2 pt-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
                          <input
                            type="file"
                            className="sr-only"
                            disabled={uploadingField === "__general__"}
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) void handleUploadTestFile(f);
                              e.target.value = "";
                            }}
                          />
                          <FileUp className="h-3.5 w-3.5 shrink-0" />
                          {uploadingField === "__general__"
                            ? "上传中…"
                            : "上传文件到 inputs/（填入路径）"}
                        </label>
                      )}
                    </div>
                  </div>

                  {isAdmin && (
                    <Button
                      className="h-9 w-full shrink-0 bg-[#1890FF] text-white hover:bg-[#1890FF]/90"
                      disabled={testing}
                      onClick={() => void handleTest()}
                    >
                      {testing ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          试运行中…
                        </>
                      ) : (
                        "试运行"
                      )}
                    </Button>
                  )}

                  {testResult && (
                    <div
                      className={`flex min-h-[140px] flex-1 flex-col overflow-hidden rounded-lg border shadow-sm ${
                        testResult.success
                          ? "border-green-200 bg-green-50/50 dark:border-green-900 dark:bg-green-950/20"
                          : "border-red-200 bg-red-50/50 dark:border-red-900 dark:bg-red-950/20"
                      }`}
                    >
                      <div className="flex items-center gap-2 border-b border-inherit bg-white/60 px-3 py-2 dark:bg-slate-950/40">
                        <Label className="text-xs font-medium">Output</Label>
                        {testResult.success ? (
                          <span className="ml-auto flex items-center gap-1 text-xs text-green-700 dark:text-green-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            成功
                          </span>
                        ) : (
                          <span className="text-destructive ml-auto flex items-center gap-1 text-xs">
                            <XCircle className="h-3.5 w-3.5" />
                            {testResult.depsError ? "依赖冲突" : "失败"}
                          </span>
                        )}
                      </div>
                      <pre className="flex-1 overflow-auto p-3 font-mono text-xs break-all whitespace-pre-wrap text-slate-800 dark:text-slate-200">
                        {testResult.success
                          ? formatTestOutput(testResult.output)
                          : testResult.logs || testResult.error || "无输出"}
                      </pre>
                      {testResult.success &&
                        testResult.outputFiles &&
                        testResult.outputFiles.length > 0 && (
                          <div className="space-y-1 border-t border-inherit px-3 pb-3">
                            <p className="pt-2 text-xs font-medium text-slate-600 dark:text-slate-400">
                              输出文件
                            </p>
                            <ul className="space-y-1">
                              {testResult.outputFiles.map((f) => (
                                <li key={f.relativePath}>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-xs text-[#1890FF] hover:text-[#1890FF]"
                                    onClick={() => {
                                      if (!selectedId) return;
                                      void downloadWorkflowToolTestFile(
                                        selectedId,
                                        f.relativePath,
                                        f.filename,
                                      ).catch((err) =>
                                        toast.error(
                                          err instanceof Error
                                            ? err.message
                                            : "下载失败",
                                        ),
                                      );
                                    }}
                                  >
                                    <Download className="mr-1 h-3.5 w-3.5" />
                                    {f.filename}
                                    <span className="ml-1 font-normal text-slate-400">
                                      ({f.relativePath})
                                    </span>
                                  </Button>
                                </li>
                              ))}
                            </ul>
                            <p className="text-[10px] text-slate-400">
                              输出文件默认写在 outputs/ 下；可直接写文件名（如
                              result.POSCAR），或设置环境变量
                              WORKFLOW_TOOL_OUTPUT_DIR
                            </p>
                          </div>
                        )}
                      {!testResult.success && (
                        <div className="space-y-1 border-t border-inherit px-3 pb-2">
                          {errorLine != null && (
                            <p className="text-xs text-red-600 dark:text-red-400">
                              错误位置：第 {errorLine} 行（已在左侧代码中标红）
                            </p>
                          )}
                          {(testResult.logs || testResult.error || "")
                            .toLowerCase()
                            .includes("docstring") && (
                            <p className="text-xs text-amber-700 dark:text-amber-400">
                              LangChain 要求 @tool
                              函数必须有文档字符串，请在函数下方添加三引号说明，例如：
                              <code className="ml-1">{`"""工具说明"""`}</code>
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <h2 className="font-semibold">
                {selected.displayName || selected.name}
              </h2>
              <p className="text-muted-foreground text-sm">
                {selected.description}
              </p>
              <div className="flex items-center gap-2">
                <Label>在工作流目录中启用</Label>
                {isAdmin ? (
                  <Button
                    size="sm"
                    variant={selected.enabled ? "default" : "outline"}
                    onClick={() => void toggleEnabled(selected)}
                  >
                    {selected.enabled ? "已启用" : "未启用"}
                  </Button>
                ) : (
                  <Badge variant={selected.enabled ? "default" : "secondary"}>
                    {selected.enabled ? "已启用" : "未启用"}
                  </Badge>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

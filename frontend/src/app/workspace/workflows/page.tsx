"use client";

import {
  Workflow as WorkflowIcon,
  RefreshCw,
  Pencil,
  Trash2,
  History,
  Wrench,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  createWorkflow,
  deleteWorkflow,
  listWorkflows,
  type Workflow,
} from "@/core/api/workflows";
import { useIsAppAdmin } from "@/hooks/use-is-app-admin";
import { cn } from "@/lib/utils";

import { CreateWorkflowDialog } from "./CreateWorkflowDialog";

export default function WorkflowsPage() {
  const router = useRouter();
  const isAdmin = useIsAppAdmin();
  const [items, setItems] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listWorkflows({ limit: 100, offset: 0 });
      setItems(data.workflows ?? []);
    } catch (e: unknown) {
      const err = e as { message?: string };
      toast.error(err?.message ?? "加载工作流失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="flex h-full flex-col bg-[#F5F5F5] dark:bg-slate-900">
      {/* 横幅：与工具箱一致 */}
      <div className="shrink-0 px-6 py-4">
        <div
          className="overflow-hidden rounded-xl bg-gradient-to-br from-[#0f172a] via-[#1e3a5f] to-[#0f172a] p-6 text-white shadow-lg dark:from-slate-900 dark:via-blue-950/50 dark:to-slate-900"
          style={{ minHeight: "120px" }}
        >
          <h2 className="mb-2 text-xl font-bold">工作流</h2>
          <p className="max-w-2xl text-sm text-white/90">
            创建、编辑与运行你的工作流，编排节点并执行任务。
          </p>
        </div>
      </div>

      {/* 操作区 */}
      <div className="shrink-0 px-6 py-2">
        <div className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          操作
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refresh()}
            disabled={loading}
            className="rounded-lg border-slate-200 bg-white text-slate-700 hover:border-[#1890FF]/40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700/50"
          >
            <RefreshCw
              className={cn("mr-1.5 h-4 w-4", loading && "animate-spin")}
            />
            刷新
          </Button>
          <Button
            size="sm"
            onClick={() => setCreateOpen(true)}
            className="rounded-lg bg-[#1890FF] text-white hover:bg-[#1890FF]/90 dark:bg-blue-600 dark:hover:bg-blue-500"
          >
            新建工作流
          </Button>
          {isAdmin && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                router.push("/workspace/workflow-tools?action=create")
              }
              className="rounded-lg border-slate-200 bg-white text-slate-700 hover:border-[#1890FF]/40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700/50"
            >
              <Wrench className="mr-1.5 h-4 w-4" />
              新建工具
            </Button>
          )}
        </div>
      </div>

      <CreateWorkflowDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={async (name, description) => {
          try {
            const wf = await createWorkflow({
              name,
              description,
              status: "draft",
            });
            toast.success("已创建工作流");
            router.push(`/workspace/workflows/${wf.id}/editor`);
          } catch (e: unknown) {
            const err = e as { message?: string };
            toast.error(err?.message ?? "创建失败");
          }
        }}
      />

      {/* 列表区：与工具箱卡片风格一致 */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex min-h-[200px] flex-col items-center justify-center text-center">
            <RefreshCw className="mb-4 h-12 w-12 animate-spin text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-[#595959] dark:text-slate-400">
              加载中…
            </p>
          </div>
        ) : items.length === 0 ? (
          <div className="flex min-h-[200px] flex-col items-center justify-center text-center">
            <div className="mb-4 w-fit rounded-xl bg-[#E6F7FF] p-3 dark:bg-blue-950/40">
              <WorkflowIcon className="h-12 w-12 text-[#1890FF] dark:text-blue-400" />
            </div>
            <p className="mb-2 text-sm text-[#595959] dark:text-slate-400">
              还没有工作流
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-500">
              点击「新建工作流」开始
            </p>
            <Button
              className="mt-4 rounded-lg bg-[#1890FF] text-white hover:bg-[#1890FF]/90"
              onClick={() => setCreateOpen(true)}
            >
              新建工作流
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((wf) => (
              <motion.div
                key={wf.id}
                whileHover={{ scale: 1.02, y: -2 }}
                whileTap={{ scale: 0.98 }}
                className={cn(
                  "block flex flex-col rounded-lg border border-slate-200 bg-white shadow-sm transition-all dark:border-slate-700 dark:bg-slate-800",
                  "hover:border-[#1890FF]/40 hover:shadow-lg",
                )}
              >
                <Link
                  href={`/workspace/workflows/${wf.id}/editor`}
                  className="flex min-w-0 flex-1 flex-col p-4"
                >
                  <div className="mb-3">
                    <div className="w-fit rounded-lg bg-[#E6F7FF] p-2 dark:bg-blue-950/40">
                      <WorkflowIcon className="h-6 w-6 text-[#1890FF] dark:text-blue-400" />
                    </div>
                  </div>
                  <h3 className="mb-1.5 line-clamp-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {wf.name}
                  </h3>
                  <p className="mb-3 line-clamp-2 flex-1 text-xs text-[#595959] dark:text-slate-400">
                    {wf.description || "—"}
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {wf.status}
                    </span>
                    <span className="text-xs text-[#1890FF] dark:text-blue-400">
                      编辑
                    </span>
                  </div>
                </Link>
                <div className="flex gap-2 border-t border-slate-100 px-4 pt-3 pb-4 dark:border-slate-700/50">
                  <Button
                    asChild
                    size="sm"
                    variant="outline"
                    className="flex-1 rounded-lg border-slate-200 dark:border-slate-600"
                  >
                    <Link
                      href={`/workspace/workflows/${wf.id}/editor`}
                      className="inline-flex items-center gap-1"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      编辑
                    </Link>
                  </Button>
                  <Button
                    asChild
                    size="sm"
                    variant="outline"
                    className="flex-1 rounded-lg border-slate-200 dark:border-slate-600"
                  >
                    <Link
                      href={`/workspace/workflows/${wf.id}/runs`}
                      className="inline-flex items-center gap-1"
                    >
                      <History className="h-3.5 w-3.5" />
                      运行历史
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-lg border-slate-200 text-red-600 hover:bg-red-50 dark:border-slate-600 dark:text-red-400 dark:hover:bg-red-950/30"
                    onClick={async (e) => {
                      e.preventDefault();
                      if (!confirm("确定删除这个工作流吗？")) return;
                      try {
                        await deleteWorkflow(wf.id);
                        toast.success("已删除");
                        refresh();
                      } catch (e: unknown) {
                        const err = e as { message?: string };
                        toast.error(err?.message ?? "删除失败");
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除
                  </Button>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getRun,
  getRunAsyncTasks,
  getRunDetail,
  getRunTasks,
  mapRunAsyncTasks,
  mapRunTasksToNodeExecutions,
  type WorkflowRunDetail,
} from "@/core/api/workflows";
import { NodeExecutionTable } from "@/components/workflow/runs/NodeExecutionTable";
import { RunExecutionGraph } from "@/components/workflow/runs/RunExecutionGraph";
import { AsyncTaskTable } from "@/components/workflow/runs/AsyncTaskTable";
import { JsonBlock } from "@/components/workflow/runs/JsonBlock";
import {
  formatDateTime,
  runStatusBadgeVariant,
  runStatusLabel,
  shouldPollRunProgress,
} from "@/components/workflow/runs/run-display-utils";

const RUN_PROGRESS_POLL_MS = 15_000;

export default function WorkflowRunDetailPage() {
  const params = useParams();
  const workflowId = String(params.id ?? "");
  const runId = String(params.runId ?? "");

  const [detail, setDetail] = useState<WorkflowRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("nodes");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [openNodeAccordionIds, setOpenNodeAccordionIds] = useState<string[]>([]);

  const load = useCallback(
    async (silent = false) => {
      if (!workflowId || !runId) return;
      if (!silent) setLoading(true);
      try {
        const detailData = await getRunDetail(workflowId, runId);
        setDetail({
          ...detailData,
          nodes: detailData.nodes ?? [],
          async_tasks: detailData.async_tasks ?? [],
        });
      } catch (e: unknown) {
        const err = e as { message?: string };
        if (!silent) toast.error(err?.message ?? "加载运行详情失败");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [workflowId, runId],
  );

  const refreshRunProgress = useCallback(async () => {
    if (!workflowId || !runId) return;
    try {
      const [run, tasks, asyncRows] = await Promise.all([
        getRun(workflowId, runId),
        getRunTasks(workflowId, runId),
        getRunAsyncTasks(workflowId, runId),
      ]);
      setDetail((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          run,
          nodes: mapRunTasksToNodeExecutions(tasks, prev.node_index),
          async_tasks: mapRunAsyncTasks(asyncRows, prev.node_index),
        };
      });
    } catch {
      /* 静默：轮询失败不打断页面 */
    }
  }, [workflowId, runId]);

  const handleSelectNodeFromGraph = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      setActiveTab("nodes");
      const row = detail?.nodes.find((n) => n.node_id === nodeId);
      if (row) {
        setOpenNodeAccordionIds((prev) =>
          prev.includes(row.id) ? prev : [...prev, row.id],
        );
      }
      window.requestAnimationFrame(() => {
        document.getElementById(`node-exec-${nodeId}`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    },
    [detail?.nodes],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const run = detail?.run;
  const status = String(run?.status ?? "unknown");

  const asyncTasks = detail?.async_tasks ?? [];
  const pollRunProgress = shouldPollRunProgress(detail);

  useEffect(() => {
    if (!pollRunProgress) return;
    const id = window.setInterval(() => void refreshRunProgress(), RUN_PROGRESS_POLL_MS);
    return () => window.clearInterval(id);
  }, [pollRunProgress, refreshRunProgress]);

  const runInput = run?.input;

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="mb-6 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">运行详情</h1>
          <p className="text-muted-foreground text-sm font-mono mt-1">{runId}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href={`/workspace/workflows/${workflowId}/runs`}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回运行历史
            </Link>
          </Button>
          <Button variant="outline" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground">加载中...</div>
      ) : !detail ? (
        <div className="text-sm text-muted-foreground">无法加载运行详情</div>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">运行概览</CardTitle>
                <Badge variant={runStatusBadgeVariant(status)}>{runStatusLabel(status)}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <RunExecutionGraph
                detail={detail}
                selectedNodeId={selectedNodeId}
                onSelectNode={handleSelectNodeFromGraph}
              />
              <div className="space-y-2 text-sm text-muted-foreground">
                <div>创建：{formatDateTime(run?.created_at as string)}</div>
                {run?.started_at ? <div>开始：{formatDateTime(run.started_at as string)}</div> : null}
                {run?.finished_at ? <div>结束：{formatDateTime(run.finished_at as string)}</div> : null}
                {run?.work_root ? (
                  <div className="font-mono text-xs break-all">工作目录：{String(run.work_root)}</div>
                ) : null}
                {runInput != null ? (
                  <div className="pt-2">
                    <JsonBlock label="运行级输入" value={runInput} maxHeightClass="max-h-[160px]" />
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList>
              <TabsTrigger value="nodes">节点执行（{detail.nodes.length}）</TabsTrigger>
              <TabsTrigger value="async">异步任务（{asyncTasks.length}）</TabsTrigger>
            </TabsList>
            <TabsContent value="nodes" className="mt-4">
              <NodeExecutionTable
                nodes={detail.nodes}
                highlightNodeId={selectedNodeId}
                openValues={openNodeAccordionIds}
                onOpenValuesChange={setOpenNodeAccordionIds}
              />
            </TabsContent>
            <TabsContent value="async" className="mt-4">
              <AsyncTaskTable tasks={asyncTasks} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}

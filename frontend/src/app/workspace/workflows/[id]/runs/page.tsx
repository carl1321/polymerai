"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listRuns, type WorkflowRun } from "@/core/api/workflow-runs";
import { runStatusBadgeVariant, runStatusLabel } from "@/components/workflow/runs/run-display-utils";

function formatDuration(started?: string, finished?: string): string | null {
  if (!started || !finished) return null;
  try {
    const ms = new Date(finished).getTime() - new Date(started).getTime();
    if (ms < 0 || !Number.isFinite(ms)) return null;
    if (ms < 1000) return `${ms} ms`;
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(1)} s`;
    return `${Math.floor(sec / 60)} m ${Math.round(sec % 60)} s`;
  } catch {
    return null;
  }
}

export default function WorkflowRunsPage() {
  const params = useParams();
  const workflowId = String(params.id ?? "");
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  const loadRuns = async () => {
    if (!workflowId) return;
    setLoading(true);
    try {
      const data = await listRuns(workflowId, { limit: 50, offset: 0 });
      setRuns(data.runs ?? []);
    } catch (e: unknown) {
      const err = e as { message?: string };
      toast.error(err?.message ?? "加载运行历史失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRuns();
  }, [workflowId]);

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">运行历史</h1>
          <p className="text-muted-foreground">工作流 ID: {workflowId}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href="/workspace/workflows">
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回工作流
            </Link>
          </Button>
          <Button variant="outline" onClick={() => void loadRuns()} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground">加载中...</div>
      ) : runs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">暂无运行记录</CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const duration = formatDuration(run.started_at, run.finished_at);
            return (
              <Link key={run.id} href={`/workspace/workflows/${workflowId}/runs/${run.id}`}>
                <Card className="transition hover:border-blue-400/40 hover:shadow-md">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">运行 {run.id.slice(0, 8)}</CardTitle>
                      <Badge variant={runStatusBadgeVariant(run.status)}>{runStatusLabel(run.status)}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-1 text-sm text-muted-foreground">
                    <div>创建：{run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "N/A"}</div>
                    {run.started_at ? <div>开始：{new Date(run.started_at).toLocaleString("zh-CN")}</div> : null}
                    {run.finished_at ? <div>结束：{new Date(run.finished_at).toLocaleString("zh-CN")}</div> : null}
                    {duration ? <div>耗时：{duration}</div> : null}
                    <div className="pt-1 text-xs text-blue-600 dark:text-blue-400">
                      点击查看节点输入/输出与异步任务
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

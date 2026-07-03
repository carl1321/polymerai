// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowUp, Bot, BookOpen, ChevronDown, ChevronRight, Copy, GitBranch, Globe, Loader2, MessageSquare, Pencil, Save, Search, Sparkles, Trash2, Upload } from "lucide-react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { PromptRichEditor } from "@/components/workspace/agents/prompt-rich-editor";
import { useRedirectOn401 } from "@/extensions/auth";
import { me } from "@/core/auth/api";
import { listAgents, getAgent, createAgent, updateAgent, deleteAgent, generateAgentPrompt } from "@/core/agents";
import {
  disablePublicLink,
  getPublicLinkStatus,
  publishAgent,
  rotatePublicToken,
} from "@/core/public-agent/api";
import { listWorkflows } from "@/core/api/workflows";
import { getSkillByName, loadSkills } from "@/core/skills/api";
import type { Skill } from "@/core/skills/type";
import { queryRAGResources } from "~/core/api/rag";
import { loadModels } from "@/core/models/api";
import type { Resource } from "~/core/messages";

/** 编排页提示词默认模板（与 agentic_workflow 一致） */
const DEFAULT_PROMPT_TEMPLATE = `# 角色
角色概述和主要职责的一句话描述
## 目标
角色的工作目标如果有多目标可以分点列出,但建议更聚焦1-2个目标
## 技能和流程说明
1. 为了实现目标角色需要具备的技能1
2. 为了实现目标角色需要具备的技能2
3. 描述角色工作流程的第一步
4. 描述角色工作流程的第二步
## 输出格式
如果对角色的输出格式有特定要求,可以在这里强调并举例说明想要的输出格式
## 限制
- 描述角色在互动过程中需要遵循的限制条件1
- 描述角色在互动过程中需要遵循的限制条件2`;

type DbAgent = {
  id: string;
  user_id?: string | null;
  name: string;
  kind?: "dedicated" | "swarm" | null;
  description?: string | null;
  system_prompt?: string | null;
  user_prompt_template?: string | null;
  opener?: string | null;
  suggested_questions?: string[] | null;
  knowledge_base_ids?: string[] | null;
  tool_names?: string[] | null;
  skill_names?: string[] | null;
  workflow_ids?: string[] | null;
  default_workflow_id?: string | null;
  model_name?: string | null;
  memory_enabled?: boolean | null;
  member_dedicated_ids?: string[] | null;
  avatar?: string | null;
  visibility?: "user" | "org" | null;
  updated_at?: string | null;
};

type AgentCreatePayload = {
  name: string;
  description?: string | null;
  system_prompt?: string | null;
  user_prompt_template?: string | null;
  opener?: string | null;
  suggested_questions?: string[] | null;
  knowledge_base_ids?: string[] | null;
  tool_names?: string[] | null;
  skill_names?: string[] | null;
  workflow_ids?: string[] | null;
  default_workflow_id?: string | null;
  model_name?: string | null;
  memory_enabled?: boolean | null;
  kind?: "dedicated" | "swarm" | null;
  member_dedicated_ids?: string[] | null;
  avatar?: string | null;
  visibility?: "user" | "org" | null;
};

interface AgentsManagementPageProps {
  onBack?: () => void;
}

export function AgentsManagementPage({ onBack }: AgentsManagementPageProps) {
  const redirectOn401 = useRedirectOn401();
  const [agents, setAgents] = useState<DbAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agentDetail, setAgentDetail] = useState<DbAgent | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [editingHeaderName, setEditingHeaderName] = useState(false);
  const [headerNameValue, setHeaderNameValue] = useState("");

  const [showStep1Dialog, setShowStep1Dialog] = useState(false);
  const [workflows, setWorkflows] = useState<{ id: string; name: string }[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [models, setModels] = useState<{ name: string; display_name?: string }[]>([]);

  const orchestrationSnapshotRef = useRef<Partial<AgentCreatePayload>>({});

  const [shareAgent, setShareAgent] = useState<DbAgent | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareInfo, setShareInfo] = useState<{
    published: boolean;
    link?: Record<string, unknown>;
  } | null>(null);
  const [shareExpiresDays, setShareExpiresDays] = useState<number>(1);
  const [lastPublishUrl, setLastPublishUrl] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);

  useEffect(() => {
    if (!shareAgent) {
      setShareInfo(null);
      setShareExpiresDays(1);
      setLastPublishUrl(null);
      setShareError(null);
      return;
    }
    let cancelled = false;
    setShareLoading(true);
    setShareError(null);
    void getPublicLinkStatus(shareAgent.id)
      .then((info) => {
        if (!cancelled) setShareInfo(info);
      })
      .catch((e) => {
        if (!cancelled)
          setShareError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setShareLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shareAgent]);

  const loadAgents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await listAgents({ page: 1, page_size: 50 });
      setAgents(res.agents as unknown as DbAgent[]);
    } catch (e) {
      if (redirectOn401(e)) return;
      setError(e instanceof Error ? e.message : String(e));
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [redirectOn401]);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    void (async () => {
      try {
        const who = await me();
        setCurrentUserId(who?.id ?? null);
        const [wfRes, skillsList, modelsList] = await Promise.all([
          listWorkflows({ limit: 100, offset: 0 }),
          loadSkills(),
          loadModels(),
        ]);
        setWorkflows((wfRes.workflows || []).map((w: any) => ({ id: w.id, name: w.name })));
        setSkills(Array.isArray(skillsList) ? skillsList : []);
        setModels((modelsList?.models ?? []).map((m: any) => ({ name: m.name, display_name: m.display_name || m.name })));
      } catch {
        // ignore
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const res = await queryRAGResources("");
        setResources(res || []);
      } catch {
        setResources([]);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setAgentDetail(null);
      setEditingHeaderName(false);
      orchestrationSnapshotRef.current = {};
      return;
    }
    void getAgent(selectedId)
      .then((a: any) => {
        const detail = a as DbAgent;
        setAgentDetail(detail);
        // Keep a full snapshot baseline so "保存" always sends full overwrite fields.
        orchestrationSnapshotRef.current = {
          system_prompt: detail.system_prompt ?? undefined,
          opener: detail.opener ?? undefined,
          knowledge_base_ids: detail.knowledge_base_ids ?? [],
          tool_names: detail.tool_names ?? [],
          skill_names: detail.kind === "swarm" ? [] : (detail.skill_names ?? []),
          workflow_ids: detail.kind === "swarm" ? [] : (detail.workflow_ids ?? []),
          model_name: detail.model_name ?? undefined,
          kind: detail.kind ?? "dedicated",
          member_dedicated_ids: detail.member_dedicated_ids ?? [],
          memory_enabled: detail.memory_enabled ?? false,
        };
      })
      .catch(() => setAgentDetail(null));
    setEditingHeaderName(false);
  }, [selectedId]);

  const handleCreateClick = () => {
    setShowStep1Dialog(true);
  };

  const handleStep1Submit = async (
    name: string,
    description: string,
    avatar: string,
    kind: "dedicated" | "swarm",
    visibility: "user" | "org",
  ) => {
    try {
      setSaving(true);
      setError(null);
      const created = (await createAgent({
        name,
        description: description || undefined,
        avatar: avatar || undefined,
        kind,
        visibility,
      } as any)) as unknown as DbAgent;
      setShowStep1Dialog(false);
      setSelectedId(created.id);
      setAgentDetail(created);
      await loadAgents();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleSelect = (id: string) => {
    setSelectedId(id);
  };

  const handleSaveNow = useCallback(async () => {
    if (!selectedId || !agentDetail) return;
    const body = {
      ...orchestrationSnapshotRef.current,
      // Force full overwrite semantics for KB binding on every save.
      knowledge_base_ids:
        orchestrationSnapshotRef.current.knowledge_base_ids ??
        agentDetail.knowledge_base_ids ??
        [],
    };
    await handleSaveEdit(body);
  }, [selectedId, agentDetail]);

  const handleSaveEdit = async (body: Partial<AgentCreatePayload>) => {
    if (!selectedId) return;
    try {
      setSaving(true);
      setError(null);
      const isSwarm = (body.kind ?? agentDetail?.kind ?? "dedicated") === "swarm";
      const payload = { ...body } as Partial<AgentCreatePayload>;
      if (isSwarm) {
        payload.skill_names = [];
        payload.workflow_ids = [];
        payload.default_workflow_id = undefined;
      }
      await updateAgent(selectedId, payload as any);
      const refreshed = (await getAgent(selectedId)) as unknown as DbAgent;
      setAgentDetail(refreshed);
      await loadAgents();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该智能体吗？")) return;
    try {
      setDeletingId(id);
      await deleteAgent(id);
      if (selectedId === id) {
        setSelectedId(null);
        setAgentDetail(null);
      }
      await loadAgents();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeletingId(null);
    }
  };

  const showBuildPanel = !!selectedId && !!agentDetail;

  if (showBuildPanel && agentDetail) {
    const canManageAgent =
      !currentUserId || !agentDetail.user_id || agentDetail.user_id === currentUserId;
    const lastSavedAt = agentDetail.updated_at
      ? new Date(agentDetail.updated_at).toLocaleString("zh-CN", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      : "未保存";

    return (
      <div className="flex h-full w-full flex-col bg-[#F5F5F5] dark:bg-slate-900">
        {error && (
          <div className="mx-6 mt-2 rounded-md bg-red-50 dark:bg-red-950/30 px-4 py-2 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {/* 顶栏：返回、头像、名称、个人空间·对话型 草稿…、编排|统计、保存、发布&集成（与 agentic_workflow 一致） */}
        <header className="shrink-0 flex items-center justify-between px-6 py-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <div className="flex items-center gap-3 min-w-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSelectedId(null)}
              className="h-8 w-8 shrink-0"
              title="返回列表"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            {editingHeaderName ? (
              <Input
                value={headerNameValue}
                onChange={(e) => setHeaderNameValue(e.target.value)}
                onBlur={async () => {
                  const v = headerNameValue.trim();
                  if (v && v !== agentDetail.name) {
                    try {
                      await updateAgent(agentDetail.id, { name: v });
                      const refreshed = (await getAgent(agentDetail.id)) as unknown as DbAgent;
                      setAgentDetail(refreshed);
                      await loadAgents();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }
                  setEditingHeaderName(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  if (e.key === "Escape") {
                    setHeaderNameValue(agentDetail.name);
                    setEditingHeaderName(false);
                  }
                }}
                className="h-8 w-[200px] text-lg font-semibold"
                autoFocus
              />
            ) : (
              <div className="flex items-center gap-1.5 min-w-0">
                <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {agentDetail.name}
                </h1>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  title="修改名称"
                  onClick={() => {
                    if (!canManageAgent) return;
                    setHeaderNameValue(agentDetail.name);
                    setEditingHeaderName(true);
                  }}
                  disabled={!canManageAgent}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
            <div className="h-8 w-8 rounded-lg bg-slate-200 dark:bg-slate-700 flex items-center justify-center overflow-hidden shrink-0">
              {agentDetail.avatar ? (
                <img src={agentDetail.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <Bot className="h-4 w-4 text-slate-500" />
              )}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
              个人空间 · 对话型 草稿最后保存于 {lastSavedAt}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleSaveNow()}
              disabled={saving || !canManageAgent}
            >
              <Save className="h-4 w-4 mr-2" />
              保存
            </Button>
            <Button
              size="sm"
              className="bg-[#1890FF] hover:bg-[#40a9ff] text-white"
              onClick={() => setShareAgent(agentDetail)}
              disabled={!canManageAgent}
            >
              发布&集成
            </Button>
          </div>
        </header>

        {/* 两栏：左 提示词 | 右 配置（去掉右侧调试预览） */}
        <div className="flex-1 flex min-h-0">
          <AgentBuildForm
            key={agentDetail.id}
            agent={agentDetail}
            canManage={canManageAgent}
            dedicatedOptions={agents.filter((a) => (a.kind ?? "dedicated") === "dedicated" && a.id !== agentDetail.id)}
            workflows={workflows}
            skills={skills}
            resources={resources}
            models={models}
            saving={saving}
            onSave={handleSaveEdit}
            onDelete={canManageAgent ? () => handleDelete(agentDetail.id) : undefined}
            onCancel={() => setSelectedId(null)}
            layout="orchestration"
            defaultPromptTemplate={DEFAULT_PROMPT_TEMPLATE}
            onSnapshotChange={(snapshot) => {
              orchestrationSnapshotRef.current = snapshot;
            }}
          />
        </div>
      </div>
    );
  }

  // 列表页：横幅 + 卡片网格
  return (
    <div className="flex h-full w-full flex-col bg-[#F5F5F5] dark:bg-slate-900">
      {error && (
        <div className="mx-6 mt-2 rounded-md bg-red-50 dark:bg-red-950/30 px-4 py-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      <div className="relative shrink-0 mx-6 mt-4 rounded-xl overflow-hidden bg-gradient-to-br from-[#0f172a] via-[#1e3a5f] to-[#0f172a] dark:from-slate-900 dark:via-blue-950/50 dark:to-slate-900 p-8 text-white shadow-lg min-height-[140px]">
        <h2 className="text-xl font-bold mb-2">智能体</h2>
        <p className="text-sm text-white/90 max-w-2xl">
          创建与管理智能体，配置人设、提示词、知识库与工具。
        </p>
        <div className="absolute right-4 bottom-4 flex gap-2">
          <Button
            onClick={handleCreateClick}
            className="bg-white text-black hover:bg-white/90 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
          >
            页面创建
          </Button>
          <Button
            onClick={onBack}
            className="bg-white text-black hover:bg-white/90 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
          >
            对话创建
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-6 py-4">
          {loading ? (
            <div className="py-12 text-center text-slate-500 dark:text-slate-400">加载中...</div>
          ) : agents.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[200px] text-center">
              <div className="w-20 h-20 rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
                <Bot className="h-10 w-10 text-slate-400 dark:text-slate-500" />
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400">暂无智能体</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
              {agents.map((a) => (
                <motion.div
                  key={a.id}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  className="group"
                >
                  <div
                    className={cn(
                      "w-full rounded-2xl border transition-all flex flex-col overflow-hidden bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 shadow-md hover:shadow-lg",
                      selectedId === a.id
                        ? "ring-2 ring-[#1890FF] dark:ring-blue-500 border-[#1890FF] dark:border-blue-500"
                        : "hover:border-slate-300 dark:hover:border-slate-600",
                    )}
                  >
                    {(() => {
                      const canManage =
                        !currentUserId || !a.user_id || a.user_id === currentUserId;
                      return (
                        <>
                    <button
                      type="button"
                      onClick={() => handleSelect(a.id)}
                      className="w-full text-left flex flex-col flex-1 min-h-0"
                      title={canManage ? "进入详情" : "可查看详情（只读）"}
                    >
                      <div className="aspect-[4/3] w-full bg-slate-100/80 dark:bg-slate-700/50 flex items-center justify-center overflow-hidden">
                        {a.avatar ? (
                          <img src={a.avatar} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <Bot className="h-16 w-16 text-slate-300 dark:text-slate-500" />
                        )}
                      </div>
                      <div className="p-5 flex flex-col gap-1.5">
                        <h3 className="font-semibold text-base text-slate-900 dark:text-slate-100 line-clamp-1">
                          {a.name}
                        </h3>
                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                          {a.description || "暂无描述"}
                        </p>
                        <div className="mt-2">
                          <span className="text-xs text-slate-400 dark:text-slate-500">
                            对话型 · {(a.visibility ?? "user") === "org" ? "公有" : "私有"}
                          </span>
                        </div>
                      </div>
                    </button>
                    <div className="px-4 pb-4 pt-0 flex items-center justify-between gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 text-slate-400 hover:text-red-600 dark:hover:text-red-400"
                        title="删除"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!canManage) return;
                          if (confirm("确定要删除该智能体吗？")) {
                            void handleDelete(a.id);
                          }
                        }}
                        disabled={deletingId === a.id || !canManage}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-9 shrink-0 text-xs"
                          title="公开访问链接"
                          onClick={(e) => {
                            e.stopPropagation();
                            setShareAgent(a);
                          }}
                        >
                          <Globe className="h-3.5 w-3.5" />
                          公开
                        </Button>
                        <Link
                          href={`/workspace/agents/${a.id}/chats/new`}
                          className="inline-flex items-center gap-2 rounded-lg bg-[#E6F7FF] dark:bg-blue-950/40 px-4 py-2.5 text-sm font-medium text-[#1890FF] dark:text-blue-400 hover:opacity-90 transition-opacity shadow-sm"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <MessageSquare className="h-4 w-4 shrink-0" />
                          对话
                        </Link>
                      </div>
                    </div>
                        </>
                      );
                    })()}
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Dialog
        open={shareAgent !== null}
        onOpenChange={(open) => {
          if (!open) setShareAgent(null);
        }}
      >
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>公开访问</DialogTitle>
            <DialogDescription>
              生成免登录链接，访客仅可与该智能体对话（不包含工作区其它功能）。请妥善保管
              token。默认有效期 1 天（24 小时），到期自动失效。你可以按天数调整。
            </DialogDescription>
          </DialogHeader>
          {shareAgent && (
            <div className="flex flex-col gap-3 text-sm">
              <p className="font-medium">{shareAgent.name}</p>
              <div className="space-y-1">
                <Label htmlFor="share-expire-days">有效期（天）</Label>
                <Input
                  id="share-expire-days"
                  type="number"
                  min={1}
                  max={365}
                  step={1}
                  value={shareExpiresDays}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (!Number.isFinite(n)) {
                      setShareExpiresDays(1);
                      return;
                    }
                    setShareExpiresDays(Math.min(365, Math.max(1, Math.floor(n))));
                  }}
                  className="w-40"
                />
                <p className="text-muted-foreground text-xs">
                  仅支持输入天数（1-365）。默认 1 天。
                </p>
              </div>
              {shareError && (
                <p className="text-destructive text-xs">{shareError}</p>
              )}
              {shareLoading && (
                <p className="text-muted-foreground text-xs">加载中…</p>
              )}
              {!shareLoading && shareInfo?.published && shareInfo.link && (
                <div className="space-y-2 rounded-md border p-3 text-xs">
                  <p>
                    已发布 · slug:{" "}
                    <code className="bg-muted rounded px-1">
                      {String(shareInfo.link.slug ?? "")}
                    </code>
                  </p>
                  <p className="text-muted-foreground">
                    完整链接中的 token 仅在创建或轮换时显示一次；若遗失请使用「轮换密钥」。
                  </p>
                </div>
              )}
              {lastPublishUrl && (
                <div className="space-y-2">
                  <p className="text-amber-600 dark:text-amber-400 text-xs font-medium">
                    请立即复制以下链接（关闭后将无法再次查看 token）：
                  </p>
                  <div className="bg-muted flex items-start gap-2 rounded-md p-2">
                    <code className="wrap-break-word grow text-[11px] leading-snug">
                      {lastPublishUrl}
                    </code>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 shrink-0"
                      title="复制"
                      onClick={() => {
                        void navigator.clipboard.writeText(lastPublishUrl);
                      }}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter className="flex flex-wrap gap-2 sm:justify-between">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={!shareAgent || shareLoading}
                onClick={() => {
                  if (!shareAgent) return;
                  setShareLoading(true);
                  setShareError(null);
                  void publishAgent(shareAgent.id, shareExpiresDays)
                    .then((res) => {
                      const full = `${typeof window !== "undefined" ? window.location.origin : ""}${res.url_path}`;
                      setLastPublishUrl(full);
                      setShareInfo({ published: true, link: { slug: res.slug } });
                    })
                    .catch((e) =>
                      setShareError(
                        e instanceof Error ? e.message : String(e),
                      ),
                    )
                    .finally(() => setShareLoading(false));
                }}
              >
                {shareInfo?.published ? "重新发布（新 token）" : "生成公开链接"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!shareAgent || !shareInfo?.published || shareLoading}
                onClick={() => {
                  if (!shareAgent) return;
                  setShareLoading(true);
                  setShareError(null);
                  void rotatePublicToken(shareAgent.id, shareExpiresDays)
                    .then((res) => {
                      const full = `${typeof window !== "undefined" ? window.location.origin : ""}${res.url_path}`;
                      setLastPublishUrl(full);
                    })
                    .catch((e) =>
                      setShareError(
                        e instanceof Error ? e.message : String(e),
                      ),
                    )
                    .finally(() => setShareLoading(false));
                }}
              >
                轮换密钥
              </Button>
            </div>
            <Button
              type="button"
              variant="destructive"
              disabled={!shareAgent || !shareInfo?.published || shareLoading}
              onClick={() => {
                if (!shareAgent) return;
                if (!confirm("确定下线公开链接？已有链接将立即失效。")) return;
                setShareLoading(true);
                setShareError(null);
                void disablePublicLink(shareAgent.id)
                  .then(() => {
                    setShareInfo({ published: false });
                    setLastPublishUrl(null);
                  })
                  .catch((e) =>
                    setShareError(e instanceof Error ? e.message : String(e)),
                  )
                  .finally(() => setShareLoading(false));
              }}
            >
              下线
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showStep1Dialog} onOpenChange={setShowStep1Dialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>创建智能体</DialogTitle>
            <DialogDescription>
              填写基本信息，创建后可进入配置页设置人设与能力。
            </DialogDescription>
          </DialogHeader>
          <Step1Form
            onSubmit={handleStep1Submit}
            onCancel={() => setShowStep1Dialog(false)}
            saving={saving}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Step1Form({
  onSubmit,
  onCancel,
  saving,
}: {
  onSubmit: (name: string, description: string, avatar: string, kind: "dedicated" | "swarm", visibility: "user" | "org") => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [avatar, setAvatar] = useState("");
  const [kind, setKind] = useState<"dedicated" | "swarm">("dedicated");
  const [visibility, setVisibility] = useState<"user" | "org">("user");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setAvatar(dataUrl);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit(name.trim(), description.trim(), avatar.trim(), kind, visibility);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 py-4">
      <div className="space-y-2">
        <Label>智能体名称 *</Label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="给智能体起一个名字"
          maxLength={128}
          required
        />
        <p className="text-xs text-slate-500">{name.length}/128</p>
      </div>
      <div className="space-y-2">
        <Label>智能体类型 *</Label>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setKind("dedicated")}
            className={cn(
              "rounded-md border px-3 py-2 text-left text-sm",
              kind === "dedicated"
                ? "border-[#1890FF] bg-[#E6F7FF] text-[#1890FF]"
                : "border-slate-200 dark:border-slate-700",
            )}
          >
            专用智能体
          </button>
          <button
            type="button"
            onClick={() => setKind("swarm")}
            className={cn(
              "rounded-md border px-3 py-2 text-left text-sm",
              kind === "swarm"
                ? "border-[#1890FF] bg-[#E6F7FF] text-[#1890FF]"
                : "border-slate-200 dark:border-slate-700",
            )}
          >
            智能体群
          </button>
        </div>
      </div>
      <div className="space-y-2">
        <Label>可见性 *</Label>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setVisibility("user")}
            className={cn(
              "rounded-md border px-3 py-2 text-left text-sm",
              visibility === "user"
                ? "border-[#1890FF] bg-[#E6F7FF] text-[#1890FF]"
                : "border-slate-200 dark:border-slate-700",
            )}
          >
            私有（仅自己）
          </button>
          <button
            type="button"
            onClick={() => setVisibility("org")}
            className={cn(
              "rounded-md border px-3 py-2 text-left text-sm",
              visibility === "org"
                ? "border-[#1890FF] bg-[#E6F7FF] text-[#1890FF]"
                : "border-slate-200 dark:border-slate-700",
            )}
          >
            公有（组织内）
          </button>
        </div>
      </div>
      <div className="space-y-2">
        <Label>智能体 logo</Label>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="h-20 w-20 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-600 flex flex-col items-center justify-center gap-1 text-slate-500 hover:border-[#1890FF] hover:text-[#1890FF] transition-colors"
          >
            <span className="text-xs">上传图片</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
          {avatar && (
            <img src={avatar} alt="" className="h-20 w-20 rounded-lg object-cover border border-slate-200" />
          )}
        </div>
      </div>
      <div className="space-y-2">
        <Label>智能体功能介绍</Label>
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="介绍智能体的功能，发布后将展示给大家"
          rows={3}
          maxLength={500}
        />
        <p className="text-xs text-slate-500">{description.length}/500</p>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "创建中…" : "确定"}
        </Button>
      </DialogFooter>
    </form>
  );
}

interface AgentBuildFormProps {
  agent: DbAgent;
  canManage: boolean;
  dedicatedOptions: DbAgent[];
  workflows: { id: string; name: string }[];
  skills: Skill[];
  resources: Resource[];
  models?: { name: string; display_name?: string }[];
  saving: boolean;
  onSave: (body: Partial<AgentCreatePayload>) => void;
  onCancel: () => void;
  onDelete?: () => void;
  layout?: "default" | "orchestration";
  defaultPromptTemplate?: string;
  /** 编排布局下右侧栏（调试与预览） */
  orchestrationRightColumn?: React.ReactNode;
  onSnapshotChange?: (snapshot: Partial<AgentCreatePayload>) => void;
}

/** Group skills by group (if set) then by category for display. */
function groupSkillsByCategory(skills: Skill[]): { groupKey: string; label: string; items: Skill[] }[] {
  const byGroup = new Map<string, Skill[]>();
  for (const s of skills) {
    const key = (s.group && s.group.trim()) || s.category || "other";
    if (!byGroup.has(key)) byGroup.set(key, []);
    byGroup.get(key)!.push(s);
  }
  const order = ["vaspagent", "agentic", "public", "custom", "other"];
  return Array.from(byGroup.entries())
    .sort(([a], [b]) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    })
    .map(([groupKey, items]) => ({
      groupKey,
      label: groupKey === "public" ? "公共" : groupKey === "custom" ? "自定义" : groupKey,
      items,
    }));
}

function AgentBuildForm({
  agent,
  canManage,
  dedicatedOptions,
  workflows,
  skills,
  resources,
  models = [],
  saving,
  onSave,
  onCancel,
  onDelete,
  layout = "default",
  defaultPromptTemplate = "",
  orchestrationRightColumn,
  onSnapshotChange,
}: AgentBuildFormProps) {
  const [name, setName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(
    agent.system_prompt?.trim() ? agent.system_prompt : (defaultPromptTemplate || "")
  );
  const [userPromptTemplate, setUserPromptTemplate] = useState(agent.user_prompt_template ?? "");
  const [opener, setOpener] = useState(agent.opener ?? "");
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>(agent.suggested_questions ?? []);
  const [suggestedInput, setSuggestedInput] = useState("");
  const [knowledgeBaseIds, setKnowledgeBaseIds] = useState<string[]>(agent.knowledge_base_ids ?? []);
  const [toolNames, setToolNames] = useState<string[]>(agent.tool_names ?? []);
  const [skillNames, setSkillNames] = useState<string[]>(agent.skill_names ?? []);
  const [workflowIds, setWorkflowIds] = useState<string[]>(agent.workflow_ids ?? []);
  const [defaultWorkflowId, setDefaultWorkflowId] = useState(agent.default_workflow_id ?? "");
  const [modelName, setModelName] = useState(agent.model_name ?? "");
  const [memoryEnabled, setMemoryEnabled] = useState(agent.memory_enabled ?? false);
  const [visibility, setVisibility] = useState<"user" | "org">((agent.visibility as "user" | "org") || "user");
  const [avatar, setAvatar] = useState(agent.avatar ?? "");
  const [skillSearchQuery, setSkillSearchQuery] = useState("");
  const [workflowSearchQuery, setWorkflowSearchQuery] = useState("");
  const [memberDedicatedIds, setMemberDedicatedIds] = useState<string[]>(
    agent.member_dedicated_ids ?? [],
  );
  const [skillGroupFilter, setSkillGroupFilter] = useState<string>("all");
  const [knowledgeSearchQuery, setKnowledgeSearchQuery] = useState("");
  const [expandedSkills, setExpandedSkills] = useState<Record<string, boolean>>({});
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [autoGenerateError, setAutoGenerateError] = useState<string | null>(null);
  const [missingSkillDetails, setMissingSkillDetails] = useState<Record<string, Skill>>({});
  const allowedKnowledgeBaseIds = useMemo(
    () => new Set(resources.map((r) => r.uri.replace("rag://dataset/", "") || r.uri)),
    [resources]
  );
  const sanitizeKnowledgeBaseIds = useCallback(
    (ids: string[]) => ids.filter((id) => allowedKnowledgeBaseIds.has(id)),
    [allowedKnowledgeBaseIds]
  );

  const displayResources = useMemo(() => {
    const seen = new Set(resources.map((r) => r.uri.replace("rag://dataset/", "") || r.uri));
    const missing = knowledgeBaseIds
      .filter((id) => !seen.has(id))
      .map((id) => ({
        uri: `rag://dataset/${id}`,
        title: `${id}（已绑定，当前不可访问）`,
      })) as Resource[];
    return [...missing, ...resources];
  }, [resources, knowledgeBaseIds]);

  useEffect(() => {
    const missing = skillNames.filter((name) => !skills.some((s) => s.name === name));
    if (missing.length === 0) {
      setMissingSkillDetails({});
      return;
    }
    let cancelled = false;
    void (async () => {
      const entries = await Promise.all(
        missing.map(async (name) => {
          try {
            const detail = await getSkillByName(name);
            return [name, detail] as const;
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      const next: Record<string, Skill> = {};
      for (const item of entries) {
        if (!item) continue;
        next[item[0]] = item[1];
      }
      setMissingSkillDetails(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [skills, skillNames]);

  const displaySkills = useMemo(() => {
    const seen = new Set(skills.map((s) => s.name));
    const missing = skillNames
      .filter((name) => !seen.has(name))
      .map((name) => missingSkillDetails[name] ?? ({
        name,
        description: "",
        category: "custom",
        license: null,
        enabled: true,
        group: "通用",
        group_name: "通用",
      })) as Skill[];
    return [...missing, ...skills];
  }, [skills, skillNames, missingSkillDetails]);

  const skillGroups = groupSkillsByCategory(displaySkills);
  const skillToolMap = (() => {
    const out: Record<string, string[]> = {};
    for (const s of displaySkills) {
      const toolList = (s.tool_names ?? []).filter((x): x is string => typeof x === "string" && x.trim().length > 0);
      out[s.name] = Array.from(new Set(toolList));
    }
    return out;
  })();

  const toggleExpandedSkill = (skillName: string) => {
    setExpandedSkills((prev) => ({ ...prev, [skillName]: !prev[skillName] }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const nextKnowledgeBaseIds = sanitizeKnowledgeBaseIds(knowledgeBaseIds);
    onSave({
      name: name.trim(),
      description: description.trim() || undefined,
      system_prompt: systemPrompt.trim() || undefined,
      user_prompt_template: userPromptTemplate.trim() || undefined,
      opener: opener.trim() || undefined,
      suggested_questions: suggestedQuestions.length ? suggestedQuestions : undefined,
      knowledge_base_ids: nextKnowledgeBaseIds,
      tool_names: toolNames.length ? toolNames : undefined,
      skill_names: agent.kind === "swarm" ? [] : skillNames,
      workflow_ids: agent.kind === "swarm" ? [] : workflowIds,
      default_workflow_id: agent.kind === "swarm" ? undefined : (defaultWorkflowId || undefined),
      model_name: modelName || undefined,
      memory_enabled: memoryEnabled,
      visibility,
      kind: (agent.kind ?? "dedicated") as "dedicated" | "swarm",
      member_dedicated_ids: agent.kind === "swarm" ? memberDedicatedIds : undefined,
      avatar: avatar.trim() || undefined,
    });
  };

  const addSuggested = () => {
    const t = suggestedInput.trim();
    if (t && !suggestedQuestions.includes(t)) {
      setSuggestedQuestions([...suggestedQuestions, t]);
      setSuggestedInput("");
    }
  };

  const removeSuggested = (i: number) => {
    setSuggestedQuestions(suggestedQuestions.filter((_, idx) => idx !== i));
  };

  const toggleKnowledge = (uri: string) => {
    const id = uri.replace("rag://dataset/", "") || uri;
    setKnowledgeBaseIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleSkill = (name: string) => {
    setSkillNames((prev) => {
      const next = prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name];
      const mergedTools = Array.from(
        new Set(
          next.flatMap((sn) => {
            const tools = skillToolMap[sn] ?? [];
            return Array.isArray(tools) ? tools : [];
          })
        )
      );
      // B 模式：取消 skill 时重新计算“已选技能工具合集”，避免交叉技能共用工具被误删。
      setToolNames(mergedTools);
      return next;
    });
  };

  const toggleTool = (toolName: string) => {
    const t = toolName.trim();
    if (!t) return;
    setToolNames((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  };

  const toggleWorkflow = (id: string) => {
    setWorkflowIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const toggleMember = (id: string) => {
    setMemberDedicatedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  useEffect(() => {
    const nextKnowledgeBaseIds = sanitizeKnowledgeBaseIds(knowledgeBaseIds);
    onSnapshotChange?.({
      system_prompt: systemPrompt.trim() || undefined,
      opener: opener.trim() || undefined,
      knowledge_base_ids: nextKnowledgeBaseIds,
      tool_names: toolNames,
      skill_names: agent.kind === "swarm" ? [] : skillNames,
      workflow_ids: agent.kind === "swarm" ? [] : workflowIds,
      model_name: modelName || undefined,
      memory_enabled: memoryEnabled,
      visibility,
      kind: (agent.kind ?? "dedicated") as "dedicated" | "swarm",
      member_dedicated_ids: agent.kind === "swarm" ? memberDedicatedIds : undefined,
    });
  }, [systemPrompt, opener, knowledgeBaseIds, toolNames, skillNames, workflowIds, modelName, memoryEnabled, visibility, agent.kind, memberDedicatedIds, onSnapshotChange, sanitizeKnowledgeBaseIds]);

  const applyAutoGenerateConfig = useCallback(async () => {
    if (!agent.id) return;
    try {
      setAutoGenerateError(null);
      setAutoGenerating(true);
      const result = await generateAgentPrompt(agent.id);
      const nextSkillNames = result.skill_names ?? [];
      const mergedTools = Array.from(
        new Set(
          nextSkillNames.flatMap((sn) => {
            const tools = skillToolMap[sn] ?? [];
            return Array.isArray(tools) ? tools : [];
          })
        )
      );
      const supplementPrompt = (result.supplement_prompt || "").trim();
      if (!supplementPrompt) return;

      setSystemPrompt(supplementPrompt);
      setSkillNames(nextSkillNames);
      setToolNames(mergedTools);
      onSave({
        system_prompt: supplementPrompt,
        skill_names: nextSkillNames,
        tool_names: mergedTools,
      });
    } catch (e) {
      setAutoGenerateError(e instanceof Error ? e.message : String(e));
    } finally {
      setAutoGenerating(false);
    }
  }, [agent.id, onSave, skillToolMap]);

  // 编排页布局：左 提示词 | 中 配置 | 右 调试与预览（与 agentic_workflow 一致）
  if (layout === "orchestration") {
    const filteredResources = knowledgeSearchQuery.trim()
      ? displayResources.filter((r) => (r.title || r.uri).toLowerCase().includes(knowledgeSearchQuery.toLowerCase()))
      : displayResources;
    const groupKeys = skillGroups.map((g) => g.groupKey);
    const baseSkills =
      skillGroupFilter === "all"
        ? displaySkills
        : displaySkills.filter((s) => ((s.group && s.group.trim()) || s.category) === skillGroupFilter);
    const filteredSkills = skillSearchQuery.trim()
      ? baseSkills.filter((s) => (s.name + " " + (s.description || "")).toLowerCase().includes(skillSearchQuery.toLowerCase()))
      : baseSkills;
    const filteredWorkflows = workflowSearchQuery.trim()
      ? workflows.filter((w) => w.name.toLowerCase().includes(workflowSearchQuery.toLowerCase()))
      : workflows;

    return (
      <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col">
        <div className="flex flex-1 min-h-0 overflow-hidden bg-slate-100/80 dark:bg-slate-800/50 gap-3 p-3">
          <div className="flex flex-1 flex-col min-w-0 min-h-0">
            <div className="shrink-0 flex items-center justify-end bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-t-xl px-4 py-2.5 border-b border-slate-200/80 dark:border-slate-700">
              <button
                type="button"
                className="flex items-center gap-1.5 text-sm font-medium hover:opacity-90 transition-opacity"
                onClick={() => {
                  if (!canManage) return;
                  void applyAutoGenerateConfig();
                }}
                disabled={!canManage || autoGenerating || saving}
              >
                {autoGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-sky-500 dark:text-sky-400" />
                    <span className="text-sky-500 dark:text-sky-400">生成中...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 text-sky-400 shrink-0" />
                    <span className="inline-flex items-baseline gap-0.5">
                      <span className="bg-gradient-to-r from-indigo-500 to-purple-600 dark:from-indigo-400 dark:to-purple-500 bg-clip-text text-transparent">AI</span>
                      <span className="text-sky-500 dark:text-sky-400">一键生成</span>
                      <span className="bg-gradient-to-r from-indigo-500 to-purple-600 dark:from-indigo-400 dark:to-purple-500 bg-clip-text text-transparent">配置</span>
                    </span>
                  </>
                )}
              </button>
              <span className="ml-3 text-xs text-slate-500 dark:text-slate-400">
                生成补充提示词，不覆盖基础技能规范
              </span>
            </div>
            {autoGenerateError ? (
              <div className="px-4 py-2 text-xs text-red-600 dark:text-red-400">
                一键生成失败：{autoGenerateError}
              </div>
            ) : null}
            <div className="flex flex-1 min-h-0 gap-3 pt-0">
              {/* 左栏：提示词（单块富文本编辑，# 角色、## 目标 等在编辑框内即加粗加大换色） */}
              <aside className="w-[520px] shrink-0 flex flex-col overflow-hidden rounded-b-xl rounded-t-none border border-t-0 border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 shadow-sm">
                <div className="flex-1 flex flex-col min-h-0 px-4 py-3 overflow-y-auto">
                  <Label className="text-sm font-medium text-[#2d9c8c] dark:text-teal-400 mb-2">提示词 ①</Label>
                  <PromptRichEditor
                    value={systemPrompt?.trim() ? systemPrompt : defaultPromptTemplate}
                    onChange={setSystemPrompt}
                    placeholder="描述角色、目标、技能与流程、输出格式、限制。使用 # 角色、## 目标 等，会显示为有色加粗加大。"
                    minHeight="280px"
                  />
                </div>
              </aside>

              {/* 中栏：配置 */}
              <main className="flex-1 min-w-0 flex flex-col overflow-hidden rounded-b-xl rounded-t-none border border-t-0 border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 shadow-sm">
                <div className="flex-1 overflow-y-auto px-5 py-4">
                  <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">配置</h2>
                  <div className="space-y-5">
                    <div>
                      <Label className="text-sm font-medium">模型</Label>
                      <select
                        value={modelName}
                        onChange={(e) => setModelName(e.target.value)}
                        className="w-full mt-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 bg-white dark:bg-slate-800"
                      >
                        <option value="">未选择</option>
                        {models.map((m) => (
                          <option key={m.name} value={m.name}>
                            {m.display_name || m.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2">
                      <div>
                        <Label className="text-sm font-medium">开启记忆</Label>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">关闭后该 Agent 不再注入和更新记忆</p>
                      </div>
                      <Switch checked={memoryEnabled} onCheckedChange={setMemoryEnabled} />
                    </div>
                    <div>
                      <Label className="text-sm font-medium">可见性</Label>
                      <select
                        value={visibility}
                        onChange={(e) => setVisibility(e.target.value as "user" | "org")}
                        className="w-full mt-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 bg-white dark:bg-slate-800"
                      >
                        <option value="user">私有（仅自己）</option>
                        <option value="org">公有（组织内）</option>
                      </select>
                    </div>
                    <div>
                      <Label className="text-sm font-medium">开场白</Label>
                      <Textarea
                        value={opener}
                        onChange={(e) => setOpener(e.target.value)}
                        placeholder="对话开始时展示"
                        rows={3}
                        className="mt-1.5 text-sm border-slate-200 dark:border-slate-600 rounded-lg resize-y"
                      />
                    </div>
                    <div>
                      <Label className="text-sm font-medium">知识库</Label>
                      <div className="relative mt-1.5">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          placeholder="搜索知识库..."
                          value={knowledgeSearchQuery}
                          onChange={(e) => setKnowledgeSearchQuery(e.target.value)}
                          className="pl-9 rounded-lg h-9"
                        />
                      </div>
                      <ScrollArea className="h-[160px] rounded-lg border border-slate-200 dark:border-slate-600 mt-2 p-2">
                        <div className="space-y-1">
                          {displayResources.length === 0 ? (
                            <p className="text-sm text-slate-500 dark:text-slate-400 py-4 text-center">暂无知识库资源</p>
                          ) : filteredResources.length === 0 ? (
                            <p className="text-sm text-slate-500 dark:text-slate-400 py-4 text-center">没有找到匹配</p>
                          ) : (
                            filteredResources.map((r) => {
                              const id = r.uri.replace("rag://dataset/", "") || r.uri;
                              const checked = knowledgeBaseIds.includes(id);
                              return (
                                <label
                                  key={r.uri}
                                  className={cn(
                                    "flex items-start gap-3 p-2 rounded-md cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors",
                                    checked && "bg-slate-100 dark:bg-slate-800"
                                  )}
                                >
                                  <Checkbox checked={checked} onCheckedChange={() => toggleKnowledge(r.uri)} className="mt-0.5" />
                                  <div className="flex-1 min-w-0 flex items-center gap-2">
                                    <BookOpen className="h-4 w-4 text-slate-500 shrink-0" />
                                    <span className="text-sm truncate">{r.title || r.uri}</span>
                                  </div>
                                </label>
                              );
                            })
                          )}
                        </div>
                      </ScrollArea>
                    </div>
                    {agent.kind === "swarm" ? (
                      <div>
                        <Label className="text-sm font-medium">子专用智能体</Label>
                        <ScrollArea className="h-[220px] rounded-lg border border-slate-200 dark:border-slate-600 mt-2 p-2">
                          <div className="space-y-1">
                            {dedicatedOptions.length === 0 ? (
                              <p className="text-sm text-slate-500 dark:text-slate-400 py-4 text-center">
                                暂无可选专用智能体
                              </p>
                            ) : (
                              dedicatedOptions.map((d) => {
                                const checked = memberDedicatedIds.includes(d.id);
                                return (
                                  <label
                                    key={d.id}
                                    className={cn(
                                      "flex items-start gap-3 p-2 rounded-md cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors",
                                      checked && "bg-slate-100 dark:bg-slate-800",
                                    )}
                                  >
                                    <Checkbox checked={checked} onCheckedChange={() => toggleMember(d.id)} className="mt-0.5" />
                                    <div className="flex-1 min-w-0">
                                      <div className="text-sm font-medium truncate">{d.name}</div>
                                      <div className="text-xs text-slate-500 dark:text-slate-400 truncate">
                                        {d.description || "暂无描述"}
                                      </div>
                                    </div>
                                  </label>
                                );
                              })
                            )}
                          </div>
                        </ScrollArea>
                      </div>
                    ) : (
                      <div>
                        <Label className="text-sm font-medium">技能</Label>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-xs text-slate-500 dark:text-slate-400">大类</span>
                        <select
                          value={skillGroupFilter}
                          onChange={(e) => setSkillGroupFilter(e.target.value)}
                          className="text-xs border border-slate-200 dark:border-slate-600 rounded-md px-2 py-1 bg-white dark:bg-slate-800"
                        >
                          <option value="all">全部</option>
                          {groupKeys.map((g) => (
                            <option key={g} value={g}>
                              {g}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="relative mt-2">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          placeholder="搜索技能..."
                          value={skillSearchQuery}
                          onChange={(e) => setSkillSearchQuery(e.target.value)}
                          className="pl-9 rounded-lg h-9"
                        />
                      </div>
                      <ScrollArea className="h-[320px] rounded-lg border border-slate-200 dark:border-slate-600 mt-2 p-2">
                        <div className="space-y-1">
                          {filteredSkills.length === 0 ? (
                            <p className="text-sm text-slate-500 dark:text-slate-400 py-4 text-center">
                              {skillSearchQuery ? "没有找到匹配的技能" : "没有可用技能"}
                            </p>
                          ) : (
                            filteredSkills.map((s) => {
                              const isSelected = skillNames.includes(s.name);
                              const tools = (s.tool_names ?? []).filter((x): x is string => typeof x === "string" && x.trim().length > 0);
                              const isExpanded = !!expandedSkills[s.name];
                              return (
                                <div
                                  key={s.name}
                                  className={cn(
                                    "rounded-md cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors",
                                    isSelected && "bg-slate-100 dark:bg-slate-800"
                                  )}
                                >
                                  <div className="flex items-start gap-3 p-2">
                                    <Checkbox checked={isSelected} onCheckedChange={() => toggleSkill(s.name)} className="mt-0.5" />
                                    <button
                                      type="button"
                                      className="flex-1 min-w-0 text-left"
                                      onClick={() => (tools.length ? toggleExpandedSkill(s.name) : undefined)}
                                    >
                                      <div className="flex items-center gap-2">
                                        {tools.length ? (
                                          isExpanded ? (
                                            <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
                                          ) : (
                                            <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
                                          )
                                        ) : (
                                          <Sparkles className="h-4 w-4 text-slate-500 shrink-0" />
                                        )}
                                        <span className="font-medium text-sm truncate">{s.name}</span>
                                        {tools.length ? (
                                          <span className="text-[11px] text-slate-500 dark:text-slate-400 shrink-0">
                                            {tools.length} 工具
                                          </span>
                                        ) : null}
                                      </div>
                                      {s.description && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">{s.description}</p>
                                      )}
                                    </button>
                                  </div>

                                  {tools.length && isExpanded ? (
                                    <div className="pb-2 pl-9 pr-2">
                                      <div className="space-y-1">
                                        {tools.map((t) => {
                                          const checked = toolNames.includes(t);
                                          return (
                                            <label
                                              key={t}
                                              className={cn(
                                                "flex items-center gap-2 rounded-md px-2 py-1 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors",
                                                checked && "bg-slate-50 dark:bg-slate-800"
                                              )}
                                            >
                                              <Checkbox checked={checked} onCheckedChange={() => toggleTool(t)} />
                                              <span className="text-xs text-slate-700 dark:text-slate-200">{t}</span>
                                            </label>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  ) : null}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </ScrollArea>
                      </div>
                    )}

                    {agent.kind !== "swarm" && (
                    <div>
                      <Label className="text-sm font-medium">工作流</Label>
                      <div className="relative mt-1.5">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          placeholder="搜索工作流..."
                          value={workflowSearchQuery}
                          onChange={(e) => setWorkflowSearchQuery(e.target.value)}
                          className="pl-9 rounded-lg h-9"
                        />
                      </div>
                      <ScrollArea className="h-[160px] rounded-lg border border-slate-200 dark:border-slate-600 mt-2 p-2">
                        <div className="space-y-1">
                          {filteredWorkflows.length === 0 ? (
                            <p className="text-sm text-slate-500 dark:text-slate-400 py-4 text-center">
                              {workflowSearchQuery ? "没有找到匹配的工作流" : "没有可用工作流"}
                            </p>
                          ) : (
                            filteredWorkflows.map((w) => {
                              const isSelected = workflowIds.includes(w.id);
                              return (
                                <label
                                  key={w.id}
                                  className={cn(
                                    "flex items-start gap-3 p-2 rounded-md cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors",
                                    isSelected && "bg-slate-100 dark:bg-slate-800"
                                  )}
                                >
                                  <Checkbox checked={isSelected} onCheckedChange={() => toggleWorkflow(w.id)} className="mt-0.5" />
                                  <div className="flex-1 min-w-0 flex items-center gap-2">
                                    <GitBranch className="h-4 w-4 text-slate-500 shrink-0" />
                                    <span className="text-sm truncate">{w.name}</span>
                                  </div>
                                </label>
                              );
                            })
                          )}
                        </div>
                      </ScrollArea>
                    </div>
                    )}
                  </div>
                </div>
              </main>
            </div>
          </div>
          {orchestrationRightColumn}
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col px-6 py-4 gap-4">
      <Tabs defaultValue="prompt" className="w-full flex-1 flex flex-col">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="prompt">提示词</TabsTrigger>
          <TabsTrigger value="basic">基本信息</TabsTrigger>
          <TabsTrigger value="knowledge">知识库</TabsTrigger>
          <TabsTrigger value="skills">技能</TabsTrigger>
          <TabsTrigger value="workflow">工作流</TabsTrigger>
          <TabsTrigger value="model">模型</TabsTrigger>
        </TabsList>

        <TabsContent value="prompt" className="space-y-4 pt-4 flex-1 overflow-y-auto">
          <div>
            <Label className="text-base font-medium">角色提示词</Label>
            <Textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="描述这个智能体的角色、目标、流程与限制"
              rows={6}
              className="font-mono text-sm mt-1"
            />
          </div>
          <div>
            <Label>用户提示词模板（可选）</Label>
            <Textarea
              value={userPromptTemplate}
              onChange={(e) => setUserPromptTemplate(e.target.value)}
              placeholder="在每次对话前附加的提示词模板，可使用 {{变量名}}"
              rows={3}
              className="font-mono text-sm mt-1"
            />
          </div>
          <div>
            <Label>开场白</Label>
            <Textarea
              value={opener}
              onChange={(e) => setOpener(e.target.value)}
              placeholder="对话开始时展示给用户的一句话介绍"
              rows={2}
              className="mt-1"
            />
          </div>
          <div>
            <Label>建议的下一步问题</Label>
            <div className="flex gap-2 mb-2 mt-1">
              <Input
                value={suggestedInput}
                onChange={(e) => setSuggestedInput(e.target.value)}
                placeholder="输入后按回车或点击添加"
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSuggested())}
              />
              <Button type="button" variant="outline" onClick={addSuggested}>
                添加
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((q, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-sm"
                >
                  {q}
                  <button
                    type="button"
                    onClick={() => removeSuggested(i)}
                    className="text-slate-500 hover:text-red-500"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="basic" className="space-y-4 pt-4 flex-1 overflow-y-auto">
          <div>
            <Label>名称 *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="智能体名称"
              required
              className="mt-1"
            />
          </div>
          <div>
            <Label>描述</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简短描述，用于展示在卡片上"
              rows={3}
              className="mt-1"
            />
          </div>
          <div>
            <Label>头像 URL（可选）</Label>
            <Input
              value={avatar}
              onChange={(e) => setAvatar(e.target.value)}
              placeholder="粘贴图片链接"
              className="mt-1"
            />
          </div>
          <div>
            <Label>可见性</Label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as "user" | "org")}
              className="w-full border rounded-md px-3 py-2 bg-white dark:bg-slate-800 mt-1 text-sm border-slate-200 dark:border-slate-600"
            >
              <option value="user">私有（仅自己）</option>
              <option value="org">公有（组织内）</option>
            </select>
          </div>
        </TabsContent>

        <TabsContent value="knowledge" className="space-y-2 pt-4 flex-1 overflow-y-auto">
          <Label>关联知识库（多选）</Label>
          <ScrollArea className="max-h-64 rounded-md border p-2 space-y-1 mt-1">
            {displayResources.length === 0 ? (
              <p className="text-sm text-slate-500">暂无知识库资源</p>
            ) : (
              displayResources.map((r) => {
                const id = r.uri.replace("rag://dataset/", "") || r.uri;
                const checked = knowledgeBaseIds.includes(id);
                return (
                  <label key={r.uri} className="flex items-center gap-2 cursor-pointer text-sm">
                    <Checkbox checked={checked} onCheckedChange={() => toggleKnowledge(r.uri)} />
                    <span className="truncate">{r.title || r.uri}</span>
                  </label>
                );
              })
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="skills" className="space-y-2 pt-4 flex-1 overflow-y-auto">
          <Label>可用技能（多选）</Label>
          <div className="relative mt-1.5">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="搜索技能..."
              className="pl-9 rounded-lg h-9"
              value={skillSearchQuery}
              onChange={(e) => setSkillSearchQuery(e.target.value)}
            />
          </div>
          <ScrollArea className="max-h-[320px] rounded-md border p-2 space-y-1 mt-2">
            {skillGroups.length === 0 ? (
              <p className="text-sm text-slate-500">没有可用技能</p>
            ) : (
              skillGroups.map(({ groupKey, label, items }) => {
                const filtered = items.filter(
                  (s) =>
                    !skillSearchQuery.trim() ||
                    (s.name + " " + (s.description || "")).toLowerCase().includes(skillSearchQuery.toLowerCase())
                );
                if (filtered.length === 0) return null;
                return (
                  <div key={groupKey} className="mb-3">
                    <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">{label}</div>
                    <div className="space-y-1">
                      {filtered.map((s) => {
                        const isSelected = skillNames.includes(s.name);
                        return (
                          <label key={s.name} className="flex items-center gap-2 cursor-pointer text-sm">
                            <Checkbox checked={isSelected} onCheckedChange={() => toggleSkill(s.name)} />
                            <Sparkles className="h-4 w-4 text-slate-500 shrink-0" />
                            <span className="truncate">{s.name}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-4 pt-4 flex-1 overflow-y-auto">
          <Label>关联工作流（多选）</Label>
          <ScrollArea className="max-h-64 rounded-md border p-2 space-y-1 mt-1">
            {workflows.length === 0 ? (
              <p className="text-sm text-slate-500">没有可用工作流</p>
            ) : (
              workflows.map((w) => {
                const isSelected = workflowIds.includes(w.id);
                return (
                  <label key={w.id} className="flex items-center gap-2 cursor-pointer text-sm">
                    <Checkbox checked={isSelected} onCheckedChange={() => toggleWorkflow(w.id)} />
                    <GitBranch className="h-4 w-4 text-slate-500" />
                    <span className="truncate">{w.name}</span>
                  </label>
                );
              })
            )}
          </ScrollArea>
          <div>
            <Label>默认工作流（单选）</Label>
            <select
              value={defaultWorkflowId}
              onChange={(e) => setDefaultWorkflowId(e.target.value)}
              className="w-full border rounded-md px-3 py-2 bg-white dark:bg-slate-800 mt-1 text-sm"
            >
              <option value="">无</option>
              {workflows
                .filter((w) => workflowIds.includes(w.id))
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
          </div>
        </TabsContent>

        <TabsContent value="model" className="space-y-4 pt-4 flex-1 overflow-y-auto">
          <Label>模型</Label>
          {models.length > 0 ? (
            <select
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              className="w-full border rounded-md px-3 py-2 bg-white dark:bg-slate-800 mt-1 text-sm border-slate-200 dark:border-slate-600"
            >
              <option value="">未选择</option>
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.display_name || m.name}
                </option>
              ))}
            </select>
          ) : (
            <Input
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="例如 doubao-1.5-pro 或自定义别名"
              className="mt-1"
            />
          )}
          <div className="flex items-center justify-between rounded-md border border-slate-200 dark:border-slate-600 px-3 py-2">
            <div>
              <Label>开启记忆</Label>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">关闭后该 Agent 不再注入和更新记忆</p>
            </div>
            <Switch checked={memoryEnabled} onCheckedChange={setMemoryEnabled} />
          </div>
        </TabsContent>
      </Tabs>

      <div className="flex gap-2 pt-4">
        <Button type="submit" disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          返回列表
        </Button>
        {onDelete && (
          <Button
            type="button"
            variant="outline"
            className="text-red-600 hover:text-red-700"
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            删除
          </Button>
        )}
      </div>
    </form>
  );
}


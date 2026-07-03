"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSkills, useUpdateSkillMetadata } from "@/core/skills/hooks";

/**
 * 技能详情页：与 agentic_workflow /tools/[toolId] 一致，含参数表单、示例、运行历史等。
 */
export default function ToolboxSkillPage() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params?.id === "string" ? params.id : "";
  const { skills, isLoading } = useSkills();
  const { mutateAsync: updateMetadata, isPending: isSaving } = useUpdateSkillMetadata();
  const skill = skills.find((s) => (s.id && s.id === id) || s.name === decodeURIComponent(id));
  const [groupName, setGroupName] = useState("");

  const handleBack = () => {
    router.push("/workspace/toolbox");
  };

  useEffect(() => {
    if (!skill) return;
    setGroupName((skill.group_name || skill.group || "").trim() || "通用");
  }, [skill]);

  const handleSaveGroup = async () => {
    if (!skill?.id) return;
    const nextGroup = (groupName || "").trim() || "通用";
    await updateMetadata({
      skillId: skill.id,
      group_name: nextGroup,
    });
  };

  const handleStartChatWithSkill = () => {
    if (!skill) return;
    router.push(`/workspace/chats/new?mode=skill&skill_name=${encodeURIComponent(skill.name)}`);
  };

  if (!skill) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center gap-4 bg-[#F5F5F5] dark:bg-slate-900 p-6">
        <p className="text-slate-600 dark:text-slate-400">{isLoading ? "加载中..." : "未找到该技能"}</p>
        <Button variant="outline" onClick={handleBack} asChild>
          <Link href="/workspace/toolbox">
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回工具箱
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col bg-[#F5F5F5] dark:bg-slate-900 p-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {(skill.laber_name || "").trim() || skill.name}
        </h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          {(skill.laber_description || "").trim() || skill.description}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>分类：{(skill.group_name || skill.group || "").trim() || "通用"}</span>
          <span>可见性：{(skill.visibility || "user") === "org" ? "公有" : "私有"}</span>
          <span>关联智能体：{(skill.agent_ids || []).length}</span>
        </div>
        <div className="mt-6 flex items-end gap-3">
          <div className="w-full max-w-xs space-y-2">
            <div className="text-xs text-slate-500">编辑分类</div>
            <Input
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="请输入分类（默认：通用）"
            />
          </div>
          <Button variant="outline" onClick={handleSaveGroup} disabled={!skill.id || isSaving}>
            {isSaving ? "保存中..." : "保存分类"}
          </Button>
        </div>
        <div className="mt-4">
          <Button onClick={handleStartChatWithSkill}>
            用该技能发起对话
          </Button>
        </div>
      </div>
    </div>
  );
}

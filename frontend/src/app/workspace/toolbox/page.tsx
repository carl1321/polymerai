"use client";

import { Play, Search } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useSkills } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

/** 常用技能 id（与参考页一致：工作流、文献搜索、数据抽取、文生图、PPT生成） */
export default function ToolboxPage() {
  const router = useRouter();
  const { skills, isLoading } = useSkills();
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const item of skills) {
      const group = (item.group_name || item.group || "").trim() || "通用";
      set.add(group);
    }
    return ["all", ...Array.from(set).sort()];
  }, [skills]);

  const filteredSkills = useMemo(() => {
    if (selectedCategory === "all") return skills;
    return skills.filter(
      (s) =>
        ((s.group_name || s.group || "").trim() || "通用") === selectedCategory,
    );
  }, [selectedCategory, skills]);

  return (
    <div className="flex h-full flex-col bg-[#F5F5F5] dark:bg-slate-900">
      {/* 智能工具箱横幅 */}
      <div className="shrink-0 px-6 py-4">
        <div
          className="relative overflow-hidden rounded-xl bg-gradient-to-br from-[#0f172a] via-[#1e3a5f] to-[#0f172a] p-8 text-white shadow-lg dark:from-slate-900 dark:via-blue-950/50 dark:to-slate-900"
          style={{ minHeight: "140px" }}
        >
          <h2 className="mb-2 text-xl font-bold">智能 SKILLS</h2>
          <p className="max-w-2xl text-sm text-white/90">
            高效聚合多种先进自动化仪器与软件平台，为科研人员快速搭建智能实验室，显著提升研发效率，释放科研潜能。
          </p>
          <div className="absolute right-4 bottom-4 flex gap-2">
            <Button
              onClick={() => {
                router.push("/workspace/skills/new");
              }}
              className="bg-white text-black hover:bg-white/90 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
            >
              页面创建
            </Button>
            <Button
              onClick={() => {
                router.push("/workspace/chats/new?mode=skill");
              }}
              className="bg-white text-black hover:bg-white/90 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
            >
              对话创建
            </Button>
          </div>
        </div>
      </div>

      {/* 分类筛选 */}
      <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-slate-200 px-6 py-2 dark:border-slate-700">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setSelectedCategory(cat)}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors",
              selectedCategory === cat
                ? "bg-[#E6F7FF] text-[#1890FF] dark:bg-blue-950/40 dark:text-blue-400"
                : "text-[#595959] hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800",
            )}
          >
            {cat === "all" ? "全部" : cat}
          </button>
        ))}
      </div>

      {/* 全部技能网格 */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="mb-4 text-sm text-[#595959] dark:text-slate-400">
            加载中...
          </div>
        ) : null}
        {filteredSkills.length === 0 ? (
          <div className="flex min-h-[200px] flex-col items-center justify-center text-center">
            <Search className="mb-4 h-12 w-12 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-[#595959] dark:text-slate-400">
              未找到匹配的工具
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredSkills.map((skill) => {
              const skillId = skill.id || encodeURIComponent(skill.name);
              const group =
                (skill.group_name || skill.group || "").trim() || "通用";
              const displayName = (skill.laber_name || "").trim() || skill.name;
              const displayDescription =
                (skill.laber_description || "").trim() || skill.description;
              return (
                <motion.div
                  key={skillId}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <button
                    type="button"
                    onClick={() => router.push(`/workspace/toolbox/${skillId}`)}
                    className={cn(
                      "block flex h-full w-full cursor-pointer flex-col rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm transition-all dark:border-slate-700 dark:bg-slate-800",
                      "border-t-[3px] border-t-[#9C27B0] dark:border-t-purple-500",
                      "hover:border-[#1890FF]/40 hover:shadow-lg active:scale-[0.98]",
                    )}
                  >
                    <div className="mb-3">
                      <div className="w-fit rounded-lg bg-[#E6F7FF] p-2 dark:bg-blue-950/40">
                        <Play className="h-6 w-6 text-[#1890FF] dark:text-blue-400" />
                      </div>
                    </div>
                    <h3 className="mb-1.5 line-clamp-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {displayName}
                    </h3>
                    <p className="mb-3 line-clamp-2 flex-1 text-xs text-[#595959] dark:text-slate-400">
                      {displayDescription}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        分类: {group}
                      </span>
                      <span className="text-xs text-slate-400">
                        {(skill.visibility || "user") === "org"
                          ? "公有"
                          : "私有"}{" "}
                        · 关联{(skill.agent_ids || []).length}
                      </span>
                    </div>
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

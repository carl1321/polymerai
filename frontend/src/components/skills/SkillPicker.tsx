// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Check, Loader2, Search } from "lucide-react";
import { getSkillByName, loadSkills } from "~/core/skills/api";
import { groupSkillsByCategory } from "~/core/skills/groupSkills";
import type { Skill } from "~/core/skills/type";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { ScrollArea } from "~/components/ui/scroll-area";
import { cn } from "~/lib/utils";

interface SkillPickerProps {
  value?: string | null;
  onChange: (skill: string | null) => void;
}

function skillTitle(skill: Skill): string {
  return (skill.laber_name && skill.laber_name.trim()) || skill.name;
}

function skillDescription(skill: Skill): string {
  const d = (skill.laber_description && skill.laber_description.trim()) || (skill.description ?? "").trim();
  if (!d) return "";
  const firstSentence = d.split(/[。.!?\n]/)[0]?.trim() || d;
  const short = firstSentence.length > 48 ? `${firstSentence.slice(0, 45)}…` : firstSentence;
  return short;
}

export function SkillPicker({ value, onChange }: SkillPickerProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [missingDetail, setMissingDetail] = useState<Skill | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const list = await loadSkills();
      setSkills(list.filter((s) => s.enabled !== false));
    } catch (e) {
      console.error("Failed to load skills", e);
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!value || skills.some((s) => s.name === value)) {
      setMissingDetail(null);
      return;
    }
    let cancelled = false;
    void getSkillByName(value)
      .then((detail) => {
        if (!cancelled) setMissingDetail(detail);
      })
      .catch(() => {
        if (!cancelled) {
          setMissingDetail({
            name: value,
            description: "技能库中未找到",
            category: "custom",
            license: null,
            enabled: true,
          } as Skill);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [value, skills]);

  const displaySkills = useMemo(() => {
    if (!value || skills.some((s) => s.name === value)) return skills;
    if (missingDetail) return [missingDetail, ...skills];
    return skills;
  }, [skills, value, missingDetail]);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return displaySkills;
    return displaySkills.filter((s) => {
      const title = skillTitle(s).toLowerCase();
      const desc = (s.description ?? "").toLowerCase();
      return s.name.toLowerCase().includes(q) || title.includes(q) || desc.includes(q);
    });
  }, [displaySkills, searchQuery]);

  const groups = useMemo(() => groupSkillsByCategory(filtered), [filtered]);

  const selectedSkill = useMemo(
    () => displaySkills.find((s) => s.name === value) ?? missingDetail,
    [displaySkills, value, missingDetail],
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-muted-foreground" />
        <Label>绑定技能</Label>
      </div>
      <p className="text-xs text-muted-foreground">
        单选一个技能；运行时将仅注入该技能的 SKILL.md，并启用 run_skill。
      </p>

      <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
        {selectedSkill ? (
          <div>
            <span className="font-medium text-foreground">{selectedSkill.name}</span>
            {skillDescription(selectedSkill) ? (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                （{skillDescription(selectedSkill)}）
              </p>
            ) : null}
          </div>
        ) : (
          <span className="text-muted-foreground">未绑定技能</span>
        )}
      </div>

      <div className="relative">
        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="搜索技能名称或描述…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8"
        />
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          加载技能库…
        </div>
      ) : (
        <ScrollArea className="h-56 rounded-md border">
          <div className="p-2 space-y-3">
            <button
              type="button"
              onClick={() => onChange(null)}
              className={cn(
                "w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted",
                !value && "bg-muted ring-1 ring-border",
              )}
            >
              <span className="font-medium">不绑定技能</span>
              <p className="text-xs text-muted-foreground mt-0.5">（纯 LLM，不注入 SKILL.md）</p>
            </button>

            {groups.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">没有匹配的技能</p>
            ) : (
              groups.map((g) => (
                <div key={g.groupKey}>
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-1">
                    {g.label}
                  </div>
                  <div className="space-y-0.5">
                    {g.items.map((skill) => {
                      const selected = value === skill.name;
                      const desc = skillDescription(skill);
                      return (
                        <button
                          key={skill.name}
                          type="button"
                          onClick={() => onChange(skill.name)}
                          className={cn(
                            "w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted",
                            selected && "bg-muted ring-1 ring-primary/40",
                          )}
                        >
                          <div className="flex items-start gap-2">
                            <div
                              className={cn(
                                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                                selected
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "border-muted-foreground/40",
                              )}
                            >
                              {selected ? <Check className="h-2.5 w-2.5" /> : null}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="font-medium text-sm text-foreground leading-tight">
                                {skill.name}
                              </div>
                              {desc ? (
                                <p className="text-xs text-muted-foreground mt-0.5 leading-snug line-clamp-1">
                                  （{desc}）
                                </p>
                              ) : (
                                <p className="text-xs text-muted-foreground mt-0.5">（{skill.name}）</p>
                              )}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}

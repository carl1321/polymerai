// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { BookOpen, Loader2, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Checkbox } from "~/components/ui/checkbox";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { ScrollArea } from "~/components/ui/scroll-area";
import { loadSkills } from "~/core/skills/api";
import type { Skill } from "~/core/skills/type";

interface SkillWhitelistSelectorProps {
  value?: string[] | null;
  onChange: (skills: string[] | null) => void;
}

export function SkillWhitelistSelector({
  value,
  onChange,
}: SkillWhitelistSelectorProps) {
  const selected = value ?? [];
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

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

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.description ?? "").toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <BookOpen className="text-muted-foreground h-4 w-4" />
        <Label>技能白名单</Label>
      </div>
      <p className="text-muted-foreground text-xs">
        勾选后仅注入对应 SKILL.md；不选任何项表示不注入技能文档。
      </p>
      <div className="relative">
        <Search className="text-muted-foreground absolute top-2.5 left-2 h-4 w-4" />
        <Input
          placeholder="搜索技能…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8"
        />
      </div>
      {loading ? (
        <div className="text-muted-foreground flex items-center gap-2 py-4 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          加载技能库…
        </div>
      ) : (
        <ScrollArea className="h-40 rounded-md border p-2">
          <div className="space-y-2">
            {filtered.map((skill) => {
              const checked = selected.includes(skill.name);
              return (
                <div key={skill.name} className="flex items-start gap-2">
                  <Checkbox
                    id={`skill-${skill.name}`}
                    checked={checked}
                    onCheckedChange={(c) => {
                      if (c) {
                        onChange([
                          ...selected.filter((n) => n !== skill.name),
                          skill.name,
                        ]);
                      } else {
                        const next = selected.filter((n) => n !== skill.name);
                        onChange(next.length ? next : []);
                      }
                    }}
                  />
                  <Label
                    htmlFor={`skill-${skill.name}`}
                    className="text-sm leading-tight font-normal"
                  >
                    {skill.name}
                    {skill.description ? (
                      <span className="text-muted-foreground block text-xs">
                        {skill.description}
                      </span>
                    ) : null}
                  </Label>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}

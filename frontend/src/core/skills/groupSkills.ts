// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { Skill } from "~/core/skills/type";

/** Group skills by group (if set) then by category for display. */
export function groupSkillsByCategory(
  skills: Skill[],
): { groupKey: string; label: string; items: Skill[] }[] {
  const byGroup = new Map<string, Skill[]>();
  for (const s of skills) {
    const key = s.group?.trim() || s.category || "other";
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
      label:
        groupKey === "public"
          ? "公共"
          : groupKey === "custom"
            ? "自定义"
            : groupKey,
      items,
    }));
}

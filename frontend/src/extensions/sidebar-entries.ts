/**
 * Extension sidebar entries (agents, toolbox, workflows).
 * Centralized so upstream layout can be replaced while keeping this config.
 * Add or remove entries here to control which extension pages appear in the sidebar.
 */

export type ExtensionSidebarIconName = "agents" | "toolbox" | "workflows";

export interface ExtensionSidebarEntry {
  href: string;
  /** I18n key under t.sidebar (e.g. "agents") or literal label */
  labelKey?: keyof (typeof import("@/core/i18n/locales/zh-CN").zhCN)["sidebar"];
  label?: string;
  /** For isActive: pathname.startsWith(pathMatch) or pathname === pathMatch */
  pathMatch: string;
  iconName: ExtensionSidebarIconName;
}

export const EXTENSION_SIDEBAR_ENTRIES: ExtensionSidebarEntry[] = [
  {
    href: "/workspace/agents",
    labelKey: "agents",
    pathMatch: "/workspace/agents",
    iconName: "agents",
  },
  {
    href: "/workspace/toolbox",
    label: "技能库",
    pathMatch: "/workspace/toolbox",
    iconName: "toolbox",
  },
  {
    href: "/workspace/workflows",
    label: "工作流",
    pathMatch: "/workspace/workflows",
    iconName: "workflows",
  },
];

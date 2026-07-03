"use client";

import { BotIcon, WrenchIcon, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import {
  EXTENSION_SIDEBAR_ENTRIES,
  type ExtensionSidebarIconName,
} from "@/extensions/sidebar-entries";

const EXTENSION_ICONS: Record<
  ExtensionSidebarIconName,
  React.ComponentType<{ className?: string }>
> = {
  agents: BotIcon,
  toolbox: WrenchIcon,
  workflows: Workflow,
};

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        {EXTENSION_SIDEBAR_ENTRIES.map((entry) => {
          const Icon = EXTENSION_ICONS[entry.iconName];
          const label =
            entry.label ?? (entry.labelKey ? t.sidebar[entry.labelKey] : entry.href);
          const isActive =
            entry.pathMatch === "/workspace/toolbox"
              ? pathname === entry.pathMatch
              : pathname.startsWith(entry.pathMatch);
          return (
            <SidebarMenuItem key={entry.href}>
              <SidebarMenuButton isActive={isActive} asChild>
                <Link className="text-muted-foreground" href={entry.href}>
                  <Icon />
                  <span>{label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}

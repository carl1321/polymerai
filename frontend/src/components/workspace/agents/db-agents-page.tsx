"use client";

import { useRouter } from "next/navigation";

import { AgentsManagementPage } from "@/components/workspace/agents/agents-management-page";

export function AgentsPage() {
  const router = useRouter();

  return (
    <AgentsManagementPage
      onBack={() => {
        // 对话创建入口：沿用原来的 /workspace/agents/new
        router.push("/workspace/agents/new");
      }}
    />
  );
}

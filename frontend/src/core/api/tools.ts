/**
 * Tool execution API: execute a tool by name with arguments.
 * List tools from config for toolbox catalog.
 * Requires app_database and toolbox routes to be enabled on the backend.
 */

import { getAuthHeaders } from "@/core/auth";
import { getBackendBaseURL } from "@/core/config";

const base = () => getBackendBaseURL() || "";

export interface ToolItem {
  name: string;
  group: string;
}

export interface ToolListResponse {
  tools: ToolItem[];
}

export interface ToolExecuteResponse {
  result: string;
  error?: string;
}

/** 获取可用工具列表（用于工具箱展示与筛选） */
export async function getToolList(): Promise<ToolItem[]> {
  const res = await fetch(`${base()}/api/tools`, {
    headers: getAuthHeaders(),
  });
  const data = (await res.json().catch(() => ({}))) as ToolListResponse;
  if (!res.ok) {
    throw new Error((data as { error?: string }).error ?? res.statusText);
  }
  return data.tools ?? [];
}

export async function executeTool(
  toolName: string,
  args: Record<string, unknown> = {},
): Promise<string> {
  const res = await fetch(`${base()}/api/tools/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ tool_name: toolName, arguments: args }),
  });
  const data = (await res.json().catch(() => ({}))) as ToolExecuteResponse;
  if (!res.ok) {
    throw new Error(data.error ?? data.result ?? res.statusText);
  }
  if (data.error) {
    throw new Error(data.error);
  }
  return data.result ?? "";
}

/**
 * Toolbox run history API (tool_run_history).
 * Requires app_database and toolbox routes to be enabled on the backend.
 */

import { getAuthHeaders } from "@/core/auth";
import { getBackendBaseURL } from "@/core/config";

const base = () => getBackendBaseURL() || "";

export interface ToolRunHistoryRecord {
  id: string;
  tool_id: string;
  params_json: Record<string, unknown> | null;
  result_json: string | null;
  created_at: string | null;
}

export interface ToolRunHistoryListResponse {
  records: ToolRunHistoryRecord[];
}

export async function saveToolRunHistory(
  toolId: string,
  params: Record<string, unknown>,
  result: string | object,
): Promise<ToolRunHistoryRecord> {
  const res = await fetch(`${base()}/api/tool-history`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({
      tool_id: toolId,
      params,
      result: typeof result === "string" ? result : JSON.stringify(result),
    }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Failed to save tool run");
  }
  return res.json();
}

export async function getToolRunHistoryList(
  options: { toolId?: string; limit?: number; offset?: number } = {},
): Promise<ToolRunHistoryListResponse> {
  const params = new URLSearchParams();
  if (options.toolId != null) params.set("tool_id", options.toolId);
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  const res = await fetch(`${base()}/api/tool-history?${params}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Failed to list tool runs");
  }
  return res.json();
}

export async function getToolRunRecord(
  recordId: string,
): Promise<ToolRunHistoryRecord> {
  const res = await fetch(`${base()}/api/tool-history/${recordId}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!res.ok) {
    if (res.status === 404) throw new Error("Record not found");
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Failed to get tool run");
  }
  return res.json();
}

export async function deleteToolRunRecord(recordId: string): Promise<void> {
  const res = await fetch(`${base()}/api/tool-history/${recordId}`, {
    method: "DELETE",
    headers: { ...getAuthHeaders() },
  });
  if (!res.ok) {
    if (res.status === 404) throw new Error("Record not found");
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Failed to delete tool run");
  }
}

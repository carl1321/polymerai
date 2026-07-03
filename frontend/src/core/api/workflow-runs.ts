import { getBackendBaseURL } from "@/core/config";
import { getAuthHeaders } from "@/core/auth";

const base = () => getBackendBaseURL() || "";

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  status: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  created_by?: string;
}

export async function listRuns(
  workflowId: string,
  params?: { limit?: number; offset?: number },
): Promise<{ runs: WorkflowRun[]; limit: number; offset: number }> {
  const qp = new URLSearchParams();
  if (params?.limit != null) qp.set("limit", String(params.limit));
  if (params?.offset != null) qp.set("offset", String(params.offset));
  const res = await fetch(`${base()}/api/workflows/${workflowId}/runs${qp.toString() ? `?${qp}` : ""}`, {
    headers: getAuthHeaders(),
  });
  const json = (await res.json().catch(() => ({}))) as {
    runs?: WorkflowRun[];
    limit?: number;
    offset?: number;
    detail?: string;
  };
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return {
    runs: json.runs ?? [],
    limit: json.limit ?? params?.limit ?? 50,
    offset: json.offset ?? params?.offset ?? 0,
  };
}


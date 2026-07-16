import { getAuthHeaders } from "@/core/auth";
import { getBackendBaseURL } from "@/core/config";

const base = () => getBackendBaseURL() || "";

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  status: string;
  current_draft_id?: string | null;
  current_release_id?: string | null;
  created_by?: string;
  created_by_name?: string | null;
  organization_id?: string | null;
  department_id?: string | null;
  workspace_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowDraft {
  id: string;
  workflow_id: string;
  version: number;
  is_autosave: boolean;
  graph: { nodes: any[]; edges: any[] };
  validation?: any;
  created_by: string;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowRelease {
  id: string;
  workflow_id: string;
  release_version?: string | number;
  source_draft_id?: string;
  spec: any;
  checksum?: string;
  created_by?: string;
  created_at?: string;
}

export async function listWorkflows(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{
  workflows: Workflow[];
  total: number;
  limit: number;
  offset: number;
}> {
  const qp = new URLSearchParams();
  if (params?.status) qp.set("status", params.status);
  if (params?.limit != null) qp.set("limit", String(params.limit));
  if (params?.offset != null) qp.set("offset", String(params.offset));
  const res = await fetch(
    `${base()}/api/workflows${qp.toString() ? `?${qp}` : ""}`,
    {
      headers: getAuthHeaders(),
    },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? res.statusText);
  return data;
}

export async function createWorkflow(data: {
  name: string;
  description?: string;
  status?: string;
}): Promise<Workflow> {
  const res = await fetch(`${base()}/api/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(data),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as Workflow;
}

export async function getWorkflow(workflowId: string): Promise<Workflow> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}`, {
    headers: getAuthHeaders(),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as Workflow;
}

export async function updateWorkflow(
  workflowId: string,
  data: { name?: string; description?: string; status?: string },
): Promise<Workflow> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(data),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as Workflow;
}

export async function deleteWorkflow(
  workflowId: string,
): Promise<{ success: boolean }> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as { success: boolean };
}

export async function saveDraft(
  workflowId: string,
  data: { graph: { nodes: any[]; edges: any[] }; is_autosave?: boolean },
): Promise<WorkflowDraft> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({
      graph: data.graph,
      is_autosave: data.is_autosave ?? false,
    }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return (json.draft ?? json) as WorkflowDraft;
}

export async function getDraft(
  workflowId: string,
  version?: number,
): Promise<WorkflowDraft> {
  const qp = new URLSearchParams();
  if (version != null) qp.set("version", String(version));
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/draft${qp.toString() ? `?${qp}` : ""}`,
    {
      headers: getAuthHeaders(),
    },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return (json.draft ?? json) as WorkflowDraft;
}

export async function listReleases(
  workflowId: string,
): Promise<WorkflowRelease[]> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}/releases`, {
    headers: getAuthHeaders(),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return (json.releases ?? []) as WorkflowRelease[];
}

export async function createRelease(
  workflowId: string,
  data: { source_draft_id: string; spec: any; checksum: string },
): Promise<WorkflowRelease> {
  const res = await fetch(`${base()}/api/workflows/${workflowId}/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(data),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return (json.release ?? json) as WorkflowRelease;
}

export async function createRun(
  workflowId: string,
  inputs: Record<string, unknown> = {},
  opts?: { source?: string; threadId?: string },
) {
  const res = await fetch(`${base()}/api/workflows/${workflowId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({
      inputs,
      source: opts?.source,
      thread_id: opts?.threadId,
    }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as { run_id: string; status: string; work_root?: string };
}

export async function uploadRunInputs(
  workflowId: string,
  runId: string,
  files: File[],
) {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/inputs`,
    {
      method: "POST",
      headers: getAuthHeaders(),
      body: form,
    },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as {
    files: { filename: string; path: string; relative: string }[];
  };
}

export async function patchRunInput(
  workflowId: string,
  runId: string,
  inputs: Record<string, unknown>,
) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/input`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ inputs }),
    },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as { input: Record<string, unknown>; work_root?: string };
}

export interface WorkflowRunNodeExecution {
  id: string;
  node_id: string;
  node_name: string;
  display_name?: string | null;
  node_type: string;
  skill?: string | null;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  input?: unknown;
  output?: unknown;
  error?: unknown;
  metrics?: unknown;
  run_seq?: number | null;
}

export interface WorkflowRunAsyncTask {
  id: string;
  task_name: string;
  job_id?: string | null;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  next_poll_at?: string | null;
  error?: unknown;
  workflow_node_id?: string | null;
  node_name?: string | null;
  task_kind?: string | null;
}

export interface WorkflowRunDetail {
  run: Record<string, unknown>;
  release_spec?: { nodes?: unknown[]; edges?: unknown[] } | null;
  node_index?: Record<
    string,
    {
      node_name: string;
      display_name?: string;
      type?: string;
      skill?: string | null;
    }
  >;
  nodes: WorkflowRunNodeExecution[];
  async_tasks: WorkflowRunAsyncTask[];
}

export async function getRun(workflowId: string, runId: string) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}`,
    { headers: getAuthHeaders() },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json.run ?? json;
}

export async function getRunDetail(
  workflowId: string,
  runId: string,
): Promise<WorkflowRunDetail> {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/detail`,
    {
      headers: getAuthHeaders(),
    },
  );
  const json = (await res.json().catch(() => ({}))) as WorkflowRunDetail & {
    detail?: string;
  };
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json;
}

/** Lightweight poll for run detail async-task tab (no full detail payload). */
export async function getRunAsyncTasks(workflowId: string, runId: string) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/async-tasks`,
    { headers: getAuthHeaders() },
  );
  const json = (await res.json().catch(() => ({}))) as {
    async_tasks?: Record<string, unknown>[];
    detail?: string;
  };
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json.async_tasks ?? [];
}

function durationMsFromTask(
  startedAt: unknown,
  finishedAt: unknown,
): number | null {
  if (!startedAt || !finishedAt) return null;
  try {
    const start = new Date(String(startedAt)).getTime();
    const end = new Date(String(finishedAt)).getTime();
    if (Number.isNaN(start) || Number.isNaN(end)) return null;
    return Math.max(0, Math.round(end - start));
  } catch {
    return null;
  }
}

function hasNonemptyTaskInput(taskInput: unknown): boolean {
  if (taskInput == null || taskInput === "") return false;
  if (typeof taskInput === "object" && !Array.isArray(taskInput)) {
    return Object.keys(taskInput).length > 0;
  }
  return true;
}

function effectiveNodeInput(taskInput: unknown, taskOutput: unknown): unknown {
  if (hasNonemptyTaskInput(taskInput)) return taskInput;
  if (
    taskOutput &&
    typeof taskOutput === "object" &&
    !Array.isArray(taskOutput)
  ) {
    const resolved = (taskOutput as Record<string, unknown>).resolved_inputs;
    if (resolved != null) return resolved;
  }
  return taskInput;
}

/** Map raw /tasks rows to detail nodes (aligned with backend enrich_node_tasks). */
export function mapRunTasksToNodeExecutions(
  tasks: Record<string, unknown>[],
  nodeIndex?: WorkflowRunDetail["node_index"],
): WorkflowRunNodeExecution[] {
  const enriched = tasks.map((task) => {
    const nid = String(task.node_id ?? "");
    const meta = nodeIndex?.[nid];
    const nodeName = meta?.node_name ?? nid;
    const output = task.output;
    return {
      id: String(task.id ?? ""),
      node_id: nid,
      node_name: nodeName,
      display_name: meta?.display_name ?? null,
      node_type: String(meta?.type ?? ""),
      skill: meta?.skill ?? null,
      status: String(task.status ?? ""),
      started_at: (task.started_at as string | null | undefined) ?? null,
      finished_at: (task.finished_at as string | null | undefined) ?? null,
      duration_ms: durationMsFromTask(task.started_at, task.finished_at),
      input: effectiveNodeInput(task.input, output),
      output,
      error: task.error,
      metrics: task.metrics,
      run_seq: (task.run_seq as number | null | undefined) ?? null,
    };
  });
  enriched.sort((a, b) => {
    const aSeq = a.run_seq;
    const bSeq = b.run_seq;
    if (aSeq == null && bSeq == null) return 0;
    if (aSeq == null) return 1;
    if (bSeq == null) return -1;
    return aSeq - bSeq;
  });
  return enriched;
}

export function mapRunAsyncTasks(
  rows: Record<string, unknown>[],
  nodeIndex?: WorkflowRunDetail["node_index"],
): WorkflowRunAsyncTask[] {
  return rows.map((row) => {
    const nid = String(row.workflow_node_id ?? "");
    const meta = nodeIndex?.[nid];
    return {
      id: String(row.id),
      task_name: String(row.display_name || row.task_kind || "async_task"),
      job_id: (row.external_ref as string | null | undefined) ?? null,
      status: String(row.status ?? ""),
      started_at: (row.created_at as string | null | undefined) ?? null,
      finished_at: (row.finished_at as string | null | undefined) ?? null,
      next_poll_at: (row.next_poll_at as string | null | undefined) ?? null,
      error: row.error,
      workflow_node_id: nid || null,
      node_name: meta?.node_name ?? null,
      task_kind: (row.task_kind as string | null | undefined) ?? null,
    };
  });
}

export async function getRunTasks(workflowId: string, runId: string) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/tasks`,
    { headers: getAuthHeaders() },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json.tasks ?? [];
}

export async function getRunLogs(
  workflowId: string,
  runId: string,
  nodeId?: string,
) {
  const qp = new URLSearchParams();
  if (nodeId) qp.set("node_id", nodeId);
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/logs${qp.toString() ? `?${qp}` : ""}`,
    { headers: getAuthHeaders() },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json.logs ?? [];
}

export async function cancelRun(workflowId: string, runId: string) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/cancel`,
    {
      method: "POST",
      headers: getAuthHeaders(),
    },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as { success: boolean };
}

export async function retryRun(workflowId: string, runId: string) {
  const res = await fetch(
    `${base()}/api/workflows/${workflowId}/runs/${runId}/retry`,
    {
      method: "POST",
      headers: getAuthHeaders(),
    },
  );
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return json as { success: boolean; status: string };
}

export async function sha256Hex(text: string): Promise<string> {
  const enc = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

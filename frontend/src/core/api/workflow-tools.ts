import { getBackendBaseURL } from "@/core/config";
import { getAuthHeaders } from "@/core/auth";

export interface WorkflowToolParameter {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
}

export interface WorkflowToolItem {
  id: string;
  name: string;
  displayName?: string;
  description: string;
  source: "script" | "builtin" | "mcp" | string;
  sourceRef?: string;
  status: string;
  enabled: boolean;
  lastTestOk?: boolean;
  requirements?: string;
  parameters: WorkflowToolParameter[];
  script?: string;
}

const CATALOG_API = "/api/workflows/tool-catalog";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBackendBaseURL() || "";
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export async function getWorkflowTool(id: string): Promise<WorkflowToolItem> {
  const data = await apiFetch<{ tool: WorkflowToolItem }>(`${CATALOG_API}/${id}`);
  return data.tool;
}

export async function listWorkflowTools(
  allStatus = false,
  scriptOnly = false,
): Promise<WorkflowToolItem[]> {
  const params = new URLSearchParams();
  if (allStatus) params.set("all_status", "true");
  if (scriptOnly) params.set("script_only", "true");
  const q = params.toString() ? `?${params.toString()}` : "";
  const data = await apiFetch<{ tools: WorkflowToolItem[] }>(`${CATALOG_API}${q}`);
  return data.tools ?? [];
}

/** User-created custom tools only (workflow_tools.source = script). */
export async function listScriptWorkflowTools(): Promise<WorkflowToolItem[]> {
  return listWorkflowTools(true, true);
}

export async function createWorkflowTool(body: {
  name: string;
  display_name: string;
  description?: string;
}): Promise<WorkflowToolItem> {
  const data = await apiFetch<{ tool: Record<string, unknown> }>(CATALOG_API, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return mapToolRow(data.tool);
}

export async function updateWorkflowTool(
  id: string,
  body: Partial<{
    display_name: string;
    description: string;
    script: string;
    requirements: string;
    enabled: boolean;
  }>,
): Promise<WorkflowToolItem> {
  const data = await apiFetch<{ tool: Record<string, unknown> }>(`${CATALOG_API}/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return mapToolRow(data.tool);
}

export interface WorkflowToolOutputFile {
  filename: string;
  relativePath: string;
  downloadUrl: string;
}

export interface TestWorkflowToolResult {
  success: boolean;
  output?: unknown;
  error?: string;
  logs?: string;
  errorLine?: number;
  depsError?: boolean;
  depsMessage?: string;
  parameters?: WorkflowToolParameter[];
  outputFiles?: WorkflowToolOutputFile[];
  inputDir?: string;
  outputDir?: string;
}

export async function testWorkflowTool(
  id: string,
  params: Record<string, unknown>,
): Promise<TestWorkflowToolResult> {
  return apiFetch<TestWorkflowToolResult>(`${CATALOG_API}/${id}/test`, {
    method: "POST",
    body: JSON.stringify({ params }),
  });
}

export async function uploadWorkflowToolTestFile(
  toolId: string,
  file: File,
  field?: string,
): Promise<{ file: { filename: string; path: string; relativePath: string }; field?: string }> {
  const base = getBackendBaseURL() || "";
  const form = new FormData();
  form.append("file", file);
  const q = field ? `?field=${encodeURIComponent(field)}` : "";
  const res = await fetch(`${base}${CATALOG_API}/${toolId}/test/upload${q}`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as { file: { filename: string; path: string; relativePath: string }; field?: string };
}

export async function downloadWorkflowToolTestFile(
  toolId: string,
  relativePath: string,
  filename: string,
): Promise<void> {
  const base = getBackendBaseURL() || "";
  const url = `${base}${CATALOG_API}/${toolId}/test/download?relativePath=${encodeURIComponent(relativePath)}`;
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = (data as { detail?: string }).detail ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}

export async function deleteWorkflowTool(id: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`${CATALOG_API}/${id}`, { method: "DELETE" });
}

export async function publishWorkflowTool(id: string): Promise<WorkflowToolItem> {
  const data = await apiFetch<{ tool: Record<string, unknown> }>(`${CATALOG_API}/${id}/publish`, {
    method: "POST",
  });
  return mapToolRow(data.tool);
}

export async function importSystemWorkflowTools(): Promise<{ imported: number }> {
  return apiFetch<{ imported: number }>(`${CATALOG_API}/import-system`, { method: "POST" });
}

export async function setWorkflowToolEnabled(id: string, enabled: boolean): Promise<WorkflowToolItem> {
  const data = await apiFetch<{ tool: Record<string, unknown> }>(`${CATALOG_API}/${id}/enabled`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  return mapToolRow(data.tool);
}

function mapToolRow(row: Record<string, unknown>): WorkflowToolItem {
  return {
    id: String(row.id ?? ""),
    name: String(row.name ?? ""),
    displayName: row.display_name != null ? String(row.display_name) : undefined,
    description: String(row.description ?? ""),
    source: String(row.source ?? "script"),
    sourceRef: row.source_ref != null ? String(row.source_ref) : undefined,
    status: String(row.status ?? "draft"),
    enabled: Boolean(row.enabled),
    lastTestOk: Boolean(row.last_test_ok),
    requirements: row.requirements != null ? String(row.requirements) : "",
    parameters: [],
    script: row.script != null ? String(row.script) : undefined,
  };
}

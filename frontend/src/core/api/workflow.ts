/**
 * Compatibility wrapper for workflow editor code imported from agentic_workflow.
 *
 * Internally calls deer-flow backend `/api/workflows*` endpoints.
 */

export * from "./workflows";

import { getBackendBaseURL } from "@/core/config";
import { getAuthHeaders } from "@/core/auth";

export interface ToolParameterDefinition {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
  default?: unknown;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameterDefinition[];
}

/** Format schema default for tool node param input. */
export function formatToolParamDefault(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Merge saved param values with tool schema defaults (only fills missing keys). */
export function buildToolParamValues(
  def: ToolDefinition | undefined,
  existing: Record<string, string> = {},
): Record<string, string> {
  const next: Record<string, string> = {};
  for (const p of def?.parameters ?? []) {
    if (Object.prototype.hasOwnProperty.call(existing, p.name)) {
      next[p.name] = existing[p.name] ?? "";
    } else {
      next[p.name] = formatToolParamDefault(p.default);
    }
  }
  return next;
}

/** For editor tool node selection. */
export async function getAvailableTools(): Promise<ToolDefinition[]> {
  const base = getBackendBaseURL() || "";
  const res = await fetch(`${base}/api/workflows/tools`, {
    headers: getAuthHeaders(),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail?: unknown }).detail)
        : res.statusText;
    throw new Error(detail || "加载工具列表失败");
  }
  if (Array.isArray(data)) {
    return (data as ToolDefinition[]).map(normalizeToolDefinition);
  }
  if (data && typeof data === "object" && Array.isArray((data as { tools?: unknown }).tools)) {
    return ((data as { tools: ToolDefinition[] }).tools).map(normalizeToolDefinition);
  }
  return [];
}

function normalizeToolDefinition(tool: ToolDefinition): ToolDefinition {
  return {
    name: tool.name,
    description: tool.description ?? "",
    parameters: Array.isArray(tool.parameters)
      ? tool.parameters.map((p) => ({
          name: p.name,
          type: p.type ?? "string",
          description: p.description,
          required: p.required,
          default: p.default,
        }))
      : [],
  };
}

export interface ExecuteWorkflowRequest {
  workflowId: string;
  inputs?: Record<string, unknown>;
  files?: string[];
  threadId?: string;
  useDraft?: boolean;
  draftId?: string;
}

export interface WorkflowExecutionEvent {
  type: "run_start" | "log" | "node_start" | "node_success" | "node_error" | "run_end" | "error";
  run_id?: string;
  node_id?: string;
  level?: string;
  event?: string;
  payload?: Record<string, unknown>;
  success?: boolean;
  error?: string;
  time?: string;
}

interface StreamEvent {
  data?: string;
}

async function* fetchStream(url: string, init: RequestInit): AsyncGenerator<StreamEvent> {
  const res = await fetch(url, init);
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `stream request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const drainEvents = (chunk: string): { events: StreamEvent[]; rest: string } => {
    const events: StreamEvent[] = [];
    const parts = chunk.split(/\r?\n\r?\n/);
    const rest = parts.pop() ?? "";
    for (const block of parts) {
      if (!block.trim()) continue;
      const dataLines = block
        .split(/\r?\n/)
        .filter((line) => line.trimStart().startsWith("data:"))
        .map((line) => line.replace(/^data:\s*/, ""));
      if (dataLines.length === 0) continue;
      events.push({ data: dataLines.join("\n") });
    }
    return { events, rest };
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      const { events } = drainEvents(buffer);
      for (const event of events) yield event;
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = drainEvents(buffer);
    buffer = rest;
    for (const event of events) yield event;
  }
}

/**
 * 原版接口：SSE 流式执行工作流。
 */
export async function* executeWorkflowStream(
  data: ExecuteWorkflowRequest,
): AsyncGenerator<WorkflowExecutionEvent> {
  const base = getBackendBaseURL() || "";
  const url = `${base}/api/workflows/execute/stream`;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
  };

  for await (const streamEvent of fetchStream(url, {
    method: "POST",
    headers,
    body: JSON.stringify({
      workflowId: data.workflowId,
      inputs: data.inputs || {},
      files: data.files,
      threadId: data.threadId,
      useDraft: data.useDraft,
      draftId: data.draftId,
    }),
  })) {
    if (!streamEvent.data) continue;
    try {
      const eventData = JSON.parse(streamEvent.data) as WorkflowExecutionEvent;
      yield eventData;
    } catch (e) {
      console.error("Failed to parse workflow event:", e, streamEvent.data);
    }
  }
}

export async function executeWorkflow(
  data: ExecuteWorkflowRequest,
): Promise<{ success: boolean; result: { run_id: string } }> {
  const base = getBackendBaseURL() || "";
  const res = await fetch(`${base}/api/workflows/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({
      workflowId: data.workflowId,
      inputs: data.inputs || {},
      files: data.files,
      threadId: data.threadId,
      useDraft: data.useDraft,
      draftId: data.draftId,
    }),
  });
  const json = (await res.json().catch(() => ({}))) as { success?: boolean; result?: { run_id: string }; detail?: string };
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return { success: !!json.success, result: json.result ?? { run_id: "" } };
}

export async function getWorkflowRun(workflowId: string, runId: string): Promise<{
  id: string;
  workflow_id: string;
  status: string;
  output?: Record<string, unknown>;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  created_by?: string;
  created_by_name?: string;
}> {
  const base = getBackendBaseURL() || "";
  const res = await fetch(`${base}/api/workflows/${workflowId}/runs/${runId}`, {
    headers: getAuthHeaders(),
  });
  const json = (await res.json().catch(() => ({}))) as {
    run?: {
      id: string;
      workflow_id: string;
      status: string;
      output?: Record<string, unknown>;
      created_at: string;
      started_at?: string;
      finished_at?: string;
      created_by?: string;
      created_by_name?: string;
    };
    detail?: string;
  };
  if (!res.ok) throw new Error(json?.detail ?? res.statusText);
  return (json.run ?? json) as {
    id: string;
    workflow_id: string;
    status: string;
    output?: Record<string, unknown>;
    created_at: string;
    started_at?: string;
    finished_at?: string;
    created_by?: string;
    created_by_name?: string;
  };
}


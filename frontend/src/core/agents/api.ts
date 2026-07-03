import { getAuthHeaders } from "@/core/auth";
import { getBackendBaseURL } from "@/core/config";

import type { Agent, CreateAgentRequest, UpdateAgentRequest } from "./types";

// DB-backed agents API, aligned with agentic_workflow Agents endpoints.
async function buildApiError(res: Response, fallback: string): Promise<Error> {
  const data = (await res.json().catch(() => ({}))) as { detail?: string };
  const detail = data.detail?.trim();
  const statusText = (res.statusText || "").trim();
  const reason = detail ?? statusText ?? fallback;
  return new Error(`${res.status} ${reason}`);
}

const BACKEND_UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

export class AgentNameCheckError extends Error {
  constructor(
    message: string,
    public readonly reason: "backend_unreachable" | "request_failed",
  ) {
    super(message);
    this.name = "AgentNameCheckError";
  }
}

export interface AgentListResponse {
  agents: Agent[];
  total: number;
  limit: number;
  offset: number;
}

export class AgentsApiDisabledError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgentsApiDisabledError";
  }
}

function isAgentsApiDisabledDetail(detail: string | undefined): boolean {
  return typeof detail === "string" && detail.includes("agents_api.enabled");
}


export interface GenerateAgentPromptResponse {
  supplement_prompt: string;
  skill_names: string[];
  matched_skills: { name: string; reason?: string }[];
  guardrail_report?: { dedup_removed: number; conflict_checked: boolean };
}

export async function listAgents(params?: {
  page?: number;
  page_size?: number;
  name?: string;
  kind?: "dedicated" | "swarm";
  /** When true, backend runs COUNT(*) for exact `total`. Default false for faster list loads. */
  include_total?: boolean;
}): Promise<AgentListResponse> {
  const search = new URLSearchParams();
  if (params?.page != null) search.set("page", String(params.page));
  if (params?.page_size != null)
    search.set("page_size", String(params.page_size));
  if (params?.name != null && params.name !== "")
    search.set("name", params.name);
  if (params?.kind != null) search.set("kind", params.kind);
  if (params?.include_total === true) search.set("include_total", "true");
  const q = search.toString();
  const res = await fetch(
    `${getBackendBaseURL()}/api/agents${q ? `?${q}` : ""}`,
    {
      headers: getAuthHeaders(),
    },
  );
  if (!res.ok) {
    throw await buildApiError(res, "Failed to load agents");
  }
  return (await res.json()) as AgentListResponse;
}

export async function getAgent(agentId: string): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${agentId}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw await buildApiError(res, `Agent '${agentId}' not found`);
  return (await res.json()) as Agent;
}

export async function createAgent(body: CreateAgentRequest): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    if (isAgentsApiDisabledDetail(err.detail)) {
      throw new AgentsApiDisabledError(err.detail!);
    }
    throw await buildApiError(res, "Failed to create agent");
  }
  return (await res.json()) as Agent;
}

export async function updateAgent(
  agentId: string,
  body: UpdateAgentRequest,
): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${agentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await buildApiError(res, "Failed to update agent");
  }
  return (await res.json()) as Agent;
}

export async function deleteAgent(agentId: string): Promise<void> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${agentId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw await buildApiError(res, "Failed to delete agent");
}

export async function checkAgentName(
  name: string,
): Promise<{ available: boolean; name: string }> {
  let res: Response;
  try {
    res = await fetch(
      `${getBackendBaseURL()}/api/agents/check?name=${encodeURIComponent(name)}`,
      { headers: getAuthHeaders() },
    );
  } catch {
    throw new AgentNameCheckError(
      "Could not reach the DeerFlow backend.",
      "backend_unreachable",
    );
  }

  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    if (isAgentsApiDisabledDetail(err.detail)) {
      throw new AgentsApiDisabledError(err.detail!);
    }
    if (BACKEND_UNAVAILABLE_STATUSES.has(res.status)) {
      throw new AgentNameCheckError(
        "Could not reach the DeerFlow backend.",
        "backend_unreachable",
      );
    }
    throw new AgentNameCheckError(
      err.detail ?? `Failed to check agent name: ${res.statusText}`,
      "request_failed",
    );
  }
  return (await res.json()) as { available: boolean; name: string };
}

export async function generateAgentPrompt(
  agentId: string,
  body?: { model_name?: string; max_skills?: number },
): Promise<GenerateAgentPromptResponse> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agents/${agentId}/generate-prompt`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(body ?? {}),
    },
  );
  if (!res.ok) {
    throw await buildApiError(res, "Failed to generate agent prompt");
  }
  return (await res.json()) as GenerateAgentPromptResponse;
}

export async function getSwarmMembers(
  agentId: string,
): Promise<{ member_dedicated_ids: string[] }> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agents/${agentId}/members`,
    {
      headers: getAuthHeaders(),
    },
  );
  if (!res.ok) {
    throw await buildApiError(res, "Failed to load swarm members");
  }
  return (await res.json()) as { member_dedicated_ids: string[] };
}

export async function replaceSwarmMembers(
  agentId: string,
  member_dedicated_ids: string[],
): Promise<{ member_dedicated_ids: string[] }> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agents/${agentId}/members`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ member_dedicated_ids }),
    },
  );
  if (!res.ok) {
    throw await buildApiError(res, "Failed to update swarm members");
  }
  return (await res.json()) as { member_dedicated_ids: string[] };
}

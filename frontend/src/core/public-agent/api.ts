import { getAuthHeaders } from "@/core/auth";
import { getBackendBaseURL } from "@/core/config";

export interface PublicMetaResponse {
  valid: boolean;
  slug: string;
  agent_id: string;
  agent_name: string;
  description: string;
  expires_at: string | null;
}

export interface PublishResponse {
  slug: string;
  token: string;
  url_path: string;
  expires_at?: string | null;
}

export async function fetchPublicMeta(
  slug: string,
  token: string,
): Promise<PublicMetaResponse> {
  const base = getBackendBaseURL();
  const url = `${base}/api/public/p/${encodeURIComponent(slug)}/meta`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? res.statusText ?? "Invalid link");
  }
  return (await res.json()) as PublicMetaResponse;
}

export async function getPublicLinkStatus(agentId: string): Promise<{
  published: boolean;
  link?: Record<string, unknown>;
}> {
  const base = getBackendBaseURL();
  const res = await fetch(
    `${base}/api/public/agents/${encodeURIComponent(agentId)}/link`,
    { headers: getAuthHeaders() },
  );
  if (!res.ok) throw new Error("Failed to load public link status");
  return (await res.json()) as {
    published: boolean;
    link?: Record<string, unknown>;
  };
}

export async function publishAgent(
  agentId: string,
  expiresInDays?: number,
): Promise<PublishResponse> {
  const base = getBackendBaseURL();
  const res = await fetch(
    `${base}/api/public/agents/${encodeURIComponent(agentId)}/publish`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(
        expiresInDays && expiresInDays > 0
          ? { expires_in_days: Math.floor(expiresInDays) }
          : {},
      ),
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? res.statusText);
  }
  return (await res.json()) as PublishResponse;
}

export async function disablePublicLink(agentId: string): Promise<void> {
  const base = getBackendBaseURL();
  const res = await fetch(
    `${base}/api/public/agents/${encodeURIComponent(agentId)}/disable`,
    { method: "POST", headers: getAuthHeaders() },
  );
  if (!res.ok) throw new Error("Failed to disable public link");
}

export async function rotatePublicToken(
  agentId: string,
  expiresInDays?: number,
): Promise<PublishResponse> {
  const base = getBackendBaseURL();
  const res = await fetch(
    `${base}/api/public/agents/${encodeURIComponent(agentId)}/rotate-token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(
        expiresInDays && expiresInDays > 0
          ? { expires_in_days: Math.floor(expiresInDays) }
          : {},
      ),
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? res.statusText);
  }
  return (await res.json()) as PublishResponse;
}

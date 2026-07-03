/** List RAG resources (knowledge bases) from backend RAGFlow proxy. */

import { getBackendBaseURL } from "@/core/config";
import { getAuthHeaders } from "@/core/auth";
import type { Resource } from "@/core/messages";

export async function queryRAGResources(query: string = ""): Promise<Resource[]> {
  try {
    const url = `${getBackendBaseURL()}/api/rag/resources?query=${encodeURIComponent(query)}`;
    const res = await fetch(url, { headers: getAuthHeaders() });
    if (!res.ok) return [];
    const data = (await res.json()) as { resources?: Resource[] };
    return data.resources ?? [];
  } catch {
    return [];
  }
}


"use client";

import { Client as LangGraphClient } from "@langchain/langgraph-sdk/client";

import { getAuthHeaders } from "../auth";
import { getToken } from "../auth/token";
import { getBackendBaseURL, getLangGraphBaseURL } from "../config";
import { isStaticWebsiteOnly } from "../static-mode";
import {
  loadStaticDemoThread,
  loadStaticDemoThreads,
  staticDemoThreadState,
} from "../threads/static-demo";
import type { AgentThreadState } from "../threads/types";

import { sanitizeRunStreamOptions } from "./stream-mode";

function createCompatibleClient(isMock?: boolean): LangGraphClient {
  if (isStaticWebsiteOnly() && !isMock) {
    return createStaticClient();
  }

  const client = new LangGraphClient({
    apiUrl: getLangGraphBaseURL(isMock),
    apiKey: null,
    defaultHeaders: getAuthHeaders(),
  });

  const originalRunStream = client.runs.stream.bind(client.runs);
  client.runs.stream = ((threadId, assistantId, payload) =>
    originalRunStream(
      threadId,
      assistantId,
      sanitizeRunStreamOptions(payload),
    )) as typeof client.runs.stream;

  const originalJoinStream = client.runs.joinStream.bind(client.runs);
  client.runs.joinStream = ((threadId, runId, options) =>
    originalJoinStream(
      threadId,
      runId,
      sanitizeRunStreamOptions(options),
    )) as typeof client.runs.joinStream;

  return client;
}

function createStaticClient(): LangGraphClient {
  const apiUrl =
    typeof window === "undefined"
      ? "http://localhost:3000"
      : window.location.origin;
  const client = new LangGraphClient({ apiUrl });

  client.threads.search = (async (query) => {
    return loadStaticDemoThreads(query);
  }) as typeof client.threads.search;

  client.threads.get = (async (threadId) => {
    return loadStaticDemoThread(threadId);
  }) as typeof client.threads.get;

  client.threads.getState = (async (threadId) => {
    return staticDemoThreadState(await loadStaticDemoThread(threadId));
  }) as typeof client.threads.getState;

  client.threads.getHistory = (async (threadId) => {
    return [staticDemoThreadState(await loadStaticDemoThread(threadId))];
  }) as typeof client.threads.getHistory;

  client.threads.update = (async (threadId) => {
    return loadStaticDemoThread(threadId);
  }) as typeof client.threads.update;

  client.runs.list = (async () => []) as typeof client.runs.list;
  client.runs.stream = async function* () {
    /* empty */
  } as typeof client.runs.stream;
  client.runs.joinStream = async function* () {
    /* empty */
  } as typeof client.runs.joinStream;

  return client as LangGraphClient<AgentThreadState>;
}

const _clients = new Map<string, LangGraphClient>();
export function getAPIClient(isMock?: boolean): LangGraphClient {
  const token = getToken() ?? "";
  const cacheKey = `${isMock ? "mock" : "default"}:${token}`;
  let client = _clients.get(cacheKey);

  if (!client) {
    client = createCompatibleClient(isMock);
    _clients.set(cacheKey, client);
  }

  return client;
}

/** LangGraph client that talks through the gateway public proxy (slug + Bearer token). Not a singleton. */
export function createPublicShareLangGraphClient(
  slug: string,
  token: string,
): LangGraphClient {
  const origin =
    typeof window !== "undefined"
      ? window.location.origin
      : "http://localhost:2026";
  const apiUrl = `${origin}/api/public/p/${encodeURIComponent(slug)}/lg`;
  const client = new LangGraphClient({
    apiUrl,
    apiKey: null,
    defaultHeaders: { Authorization: `Bearer ${token}` },
  });

  const originalRunStream = client.runs.stream.bind(client.runs);
  client.runs.stream = ((threadId, assistantId, payload) =>
    originalRunStream(
      threadId,
      assistantId,
      sanitizeRunStreamOptions(payload),
    )) as typeof client.runs.stream;

  const originalJoinStream = client.runs.joinStream.bind(client.runs);
  client.runs.joinStream = ((threadId, runId, options) =>
    originalJoinStream(
      threadId,
      runId,
      sanitizeRunStreamOptions(options),
    )) as typeof client.runs.joinStream;

  return client;
}

/**
 * 通用网关 API 请求函数（兼容 agentic_workflow 风格）。
 * path 不需要以 /api 开头，例如 "new-sam/execution-history"。
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const base = getBackendBaseURL() || "";
  const url = `${base}/api${normalizedPath}`;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
    ...(init?.headers ?? {}),
  };
  const res = await fetch(url, { ...init, headers });
  const json = (await res.json().catch(() => ({})));
  if (!res.ok) {
    throw new Error(json?.detail ?? res.statusText ?? "Request failed");
  }
  return json as T;
}

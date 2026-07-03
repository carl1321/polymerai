import { getAuthHeaders } from "../auth/token";
import { getBackendBaseURL } from "../config";

const JOIN_ATTEMPTS = 3;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

export async function fetchThreadActiveRunId(
  threadId: string,
  signal: AbortSignal,
): Promise<string | null> {
  const base = (getBackendBaseURL() ?? "").replace(/\/+$/, "");
  const res = await fetch(
    `${base}/api/threads/${encodeURIComponent(threadId)}/runs?limit=15`,
    { headers: getAuthHeaders(), signal },
  );
  if (!res.ok) {
    return null;
  }
  const runs = (await res.json()) as Array<{
    run_id?: string;
    status?: string;
  }>;
  if (!Array.isArray(runs)) {
    return null;
  }
  const active = runs.find(
    (r) => r.status === "running" || r.status === "pending",
  );
  return typeof active?.run_id === "string" ? active.run_id : null;
}

export type JoinActiveRunOptions = {
  /**
   * When `false`, re-join even if sessionStorage already matches the active run
   * (e.g. SSE died but the server run is still running). When `true` or omitted,
   * same run id skips join so a healthy in-flight stream is not doubled.
   */
  isStreamLoading?: boolean | (() => boolean);
};

function resolveStreamLoading(
  opts: JoinActiveRunOptions | undefined,
): boolean | undefined {
  const v = opts?.isStreamLoading;
  if (typeof v === "function") {
    return v();
  }
  return v;
}

/**
 * Join the active run when there is no in-flight stream key, or when the active
 * run id differs from sessionStorage (e.g. new follow-up run). Retries with backoff
 * on transient failures. Skips when storage already matches the active run unless
 * `isStreamLoading === false` (reconcile: server still running, client stream idle).
 */
export async function joinActiveRunIfStaleOrMissing(
  threadId: string,
  storage: Pick<Storage, "getItem"> | null | undefined,
  joinStream: (runId: string, lastEventId?: string) => Promise<unknown>,
  signal: AbortSignal,
  opts?: JoinActiveRunOptions,
): Promise<void> {
  try {
    const streamKey = `lg:stream:${threadId}`;
    const stored = storage?.getItem(streamKey) ?? null;
    const activeRunId = await fetchThreadActiveRunId(threadId, signal);
    if (!activeRunId) {
      return;
    }
    const loading = resolveStreamLoading(opts);
    if (stored === activeRunId && loading !== false) {
      return;
    }
    for (let attempt = 0; attempt < JOIN_ATTEMPTS; attempt++) {
      if (signal.aborted) {
        return;
      }
      if (attempt > 0) {
        await sleep(500 * 2 ** (attempt - 1));
      }
      if (signal.aborted) {
        return;
      }
      try {
        await joinStream(activeRunId);
        return;
      } catch (err) {
        if (signal.aborted || isAbortError(err)) {
          return;
        }
        /* retry */
      }
    }
  } catch (err) {
    if (signal.aborted || isAbortError(err)) {
      return;
    }
    throw err;
  }
}

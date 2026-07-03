import { getAuthHeaders } from "../auth/token";
import { getBackendBaseURL } from "../config";

export type ThreadAsyncTaskApiRow = {
  id: string;
  task_kind: string;
  status: string;
  display_name: string | null;
  external_ref: string | null;
  source_run_id: string | null;
  source_tool_call_id: string | null;
  created_at: string;
  updated_at: string;
  next_poll_at: string | null;
  finished_at: string | null;
  terminal_followup_done: boolean;
  /** Present when backend exposes it (same shell command the async dispatcher runs). */
  poll_command?: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
};

function threadsApiBase(): string {
  return (getBackendBaseURL() ?? "").replace(/\/+$/, "");
}

export async function fetchThreadAsyncTasks(
  threadId: string,
): Promise<ThreadAsyncTaskApiRow[] | null> {
  const base = threadsApiBase();
  const url = `${base}/api/threads/${encodeURIComponent(threadId)}/async_tasks`;
  const res = await fetch(url, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...getAuthHeaders(),
    },
  });
  if (res.status === 503 || res.status === 404) {
    return null;
  }
  if (!res.ok) {
    return null;
  }
  const data = (await res.json()) as unknown;
  if (!Array.isArray(data)) {
    return null;
  }
  return data as ThreadAsyncTaskApiRow[];
}

type SseFrame = { event: string; data: string };

function splitSseFrames(buffer: string): { rest: string; frames: SseFrame[] } {
  const frames: SseFrame[] = [];
  let rest = buffer;
  while (true) {
    const sep = rest.indexOf("\n\n");
    if (sep < 0) {
      break;
    }
    const raw = rest.slice(0, sep);
    rest = rest.slice(sep + 2);
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length > 0) {
      frames.push({ event, data: dataLines.join("\n") });
    }
  }
  return { rest, frames };
}

/**
 * Optional SSE reader for thread-level async_task events (not used by main chat UI).
 * Task cards use `GET /api/threads/{id}/async_tasks` plus visibility refetch; see STREAMING.md.
 */
export async function consumeThreadAsyncTasksSse(
  threadId: string,
  signal: AbortSignal,
  onCustomJson: (payload: Record<string, unknown>) => void,
): Promise<void> {
  const base = threadsApiBase();
  const url = `${base}/api/threads/${encodeURIComponent(threadId)}/async_tasks/stream`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      ...getAuthHeaders(),
    },
    signal,
  });
  if (!res.ok || !res.body) {
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let carry = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      carry += decoder.decode(value, { stream: true });
      const { rest, frames } = splitSseFrames(carry);
      carry = rest;
      for (const frame of frames) {
        if (frame.event !== "custom") {
          continue;
        }
        try {
          const payload = JSON.parse(frame.data) as Record<string, unknown>;
          onCustomJson(payload);
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  } catch {
    /* aborted or network */
  } finally {
    reader.releaseLock();
  }
}

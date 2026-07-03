import type { AIMessage, Message, Run } from "@langchain/langgraph-sdk";
import type {
  Client as LangGraphClient,
  ThreadsClient,
} from "@langchain/langgraph-sdk/client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { env } from "@/env";

import { getAPIClient } from "../api";
import {
  fetchThreadAsyncTasks,
  type ThreadAsyncTaskApiRow,
} from "../api/async-tasks";
import { getAuthHeaders, getJwtSubject, getToken } from "../auth/token";
import { getBackendBaseURL } from "../config";
import { useI18n } from "../i18n/hooks";
import {
  createAsyncTaskProgressMessage,
  type FileInMessage,
} from "../messages/utils";
import type { LocalSettings } from "../settings";
import { useUpdateSubtask } from "../tasks/context";
import type { UploadedFileInfo } from "../uploads";
import { promptInputFilePartToFile, uploadFiles } from "../uploads";

import {
  errorSummaryLine,
  formatAsyncTaskMarkdown,
  resultSummaryForToast,
  threadAsyncTaskApiRowToUi,
  type ThreadAsyncTaskUiState,
} from "./async-task-card";
import { joinActiveRunIfStaleOrMissing } from "./join-active-run";
import { fetchThreadTokenUsage } from "./api";
import { threadTokenUsageQueryKey } from "./token-usage";
import type {
  AgentThread,
  AgentThreadState,
  RunMessage,
  ThreadTokenUsageResponse,
} from "./types";

/** Thread row from POST /api/threads/search (Gateway ThreadResponse). */
type GatewayThreadRow = {
  thread_id: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  values?: Record<string, unknown>;
  interrupts?: Record<string, unknown>;
};

function mapGatewayThreadToAgentThread(row: GatewayThreadRow): AgentThread {
  const values = row.values ?? {};
  const title =
    typeof values.title === "string" && values.title.trim() ? values.title : "";
  return {
    thread_id: row.thread_id,
    created_at: row.created_at ?? "",
    updated_at: row.updated_at ?? "",
    metadata: row.metadata ?? {},
    values: {
      ...values,
      title,
      messages: Array.isArray(values.messages) ? values.messages : [],
      artifacts: Array.isArray(values.artifacts) ? values.artifacts : [],
    } as AgentThreadState,
    status: row.status ?? "idle",
    interrupts: row.interrupts ?? {},
  } as AgentThread;
}

function sortThreadsNewestFirst(threads: AgentThread[]): AgentThread[] {
  return [...threads].sort((a, b) => {
    const aUpdated = Date.parse(a.updated_at || "");
    const bUpdated = Date.parse(b.updated_at || "");
    if (
      !Number.isNaN(aUpdated) &&
      !Number.isNaN(bUpdated) &&
      aUpdated !== bUpdated
    ) {
      return bUpdated - aUpdated;
    }
    const aCreated = Date.parse(a.created_at || "");
    const bCreated = Date.parse(b.created_at || "");
    if (
      !Number.isNaN(aCreated) &&
      !Number.isNaN(bCreated) &&
      aCreated !== bCreated
    ) {
      return bCreated - aCreated;
    }
    return b.thread_id.localeCompare(a.thread_id);
  });
}

async function searchThreadsViaGateway(
  params?: Parameters<ThreadsClient["search"]>[0],
): Promise<AgentThread[]> {
  const p = params ?? {};
  const base = (getBackendBaseURL() ?? "").replace(/\/+$/, "");
  const searchUrl = `${base}/api/threads/search`;
  const maxResults = p.limit;
  const initialOffset = p.offset ?? 0;
  const DEFAULT_PAGE_SIZE = 50;
  const metadata =
    p.metadata && typeof p.metadata === "object"
      ? (p.metadata as Record<string, unknown>)
      : {};
  const status =
    typeof p.status === "string" && p.status.trim() ? p.status : undefined;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
  };

  const fetchPage = async (limit: number, offset: number) => {
    const body: Record<string, unknown> = {
      metadata,
      limit,
      offset,
    };
    if (status !== undefined) {
      body.status = status;
    }
    const res = await fetch(searchUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const json = (await res.json().catch(() => [])) as unknown;
    if (res.status === 401 || res.status === 403) {
      return [];
    }
    if (!res.ok) {
      const detail =
        typeof json === "object" &&
        json !== null &&
        "detail" in json &&
        typeof (json as { detail: unknown }).detail === "string"
          ? (json as { detail: string }).detail
          : res.statusText;
      throw new Error(detail);
    }
    if (!Array.isArray(json)) {
      return [];
    }
    return json.map((row) =>
      mapGatewayThreadToAgentThread(row as GatewayThreadRow),
    );
  };

  if (maxResults !== undefined && maxResults <= 0) {
    return fetchPage(p.limit ?? 0, initialOffset);
  }

  const pageSize =
    typeof maxResults === "number" && maxResults > 0
      ? Math.min(DEFAULT_PAGE_SIZE, maxResults)
      : DEFAULT_PAGE_SIZE;

  const threads: AgentThread[] = [];
  let offset = initialOffset;

  while (true) {
    if (typeof maxResults === "number" && threads.length >= maxResults) {
      break;
    }

    const currentLimit =
      typeof maxResults === "number"
        ? Math.min(pageSize, maxResults - threads.length)
        : pageSize;

    if (typeof maxResults === "number" && currentLimit <= 0) {
      break;
    }

    const page = await fetchPage(currentLimit, offset);
    threads.push(...page);

    if (page.length < currentLimit) {
      break;
    }

    offset += page.length;
  }

  return sortThreadsNewestFirst(threads);
}

export type ToolEndEvent = {
  name: string;
  data: unknown;
};

export type ThreadStreamOptions = {
  threadId?: string | null | undefined;
  context: LocalSettings["context"];
  isMock?: boolean;
  /** When set, used instead of the global LangGraph client (e.g. public share proxy). */
  langGraphClient?: LangGraphClient;
  onSend?: (threadId: string) => void;
  onStart?: (threadId: string) => void;
  onFinish?: (state: AgentThreadState) => void;
  onToolEnd?: (event: ToolEndEvent) => void;
};

type SendMessageOptions = {
  additionalKwargs?: Record<string, unknown>;
};

type RunEndPayload = {
  finished_at?: string;
  finished_at_ms?: number;
  duration_ms?: number;
  started_at?: string;
};

function normalizeStoredRunId(runId: string | null): string | null {
  if (!runId) {
    return null;
  }

  const trimmed = runId.trim();
  if (!trimmed) {
    return null;
  }

  const queryIndex = trimmed.indexOf("?");
  if (queryIndex >= 0) {
    const params = new URLSearchParams(trimmed.slice(queryIndex + 1));
    const queryRunId = params.get("run_id")?.trim();
    if (queryRunId) {
      return queryRunId;
    }
  }

  const pathWithoutQueryOrHash = trimmed.split(/[?#]/, 1)[0]?.trim() ?? "";
  if (!pathWithoutQueryOrHash) {
    return null;
  }

  const runsMarker = "/runs/";
  const runsIndex = pathWithoutQueryOrHash.lastIndexOf(runsMarker);
  if (runsIndex >= 0) {
    const runIdAfterMarker = pathWithoutQueryOrHash
      .slice(runsIndex + runsMarker.length)
      .split("/", 1)[0]
      ?.trim();
    if (runIdAfterMarker) {
      return runIdAfterMarker;
    }
    return null;
  }

  const segments = pathWithoutQueryOrHash
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
  return segments.at(-1) ?? null;
}

function getRunMetadataStorage(): {
  getItem(key: `lg:stream:${string}`): string | null;
  setItem(key: `lg:stream:${string}`, value: string): void;
  removeItem(key: `lg:stream:${string}`): void;
} {
  return {
    getItem(key) {
      const normalized = normalizeStoredRunId(
        window.sessionStorage.getItem(key),
      );
      if (normalized) {
        window.sessionStorage.setItem(key, normalized);
        return normalized;
      }
      window.sessionStorage.removeItem(key);
      return null;
    },
    setItem(key, value) {
      const normalized = normalizeStoredRunId(value);
      if (normalized) {
        window.sessionStorage.setItem(key, normalized);
        return;
      }
      window.sessionStorage.removeItem(key);
    },
    removeItem(key) {
      window.sessionStorage.removeItem(key);
    },
  };
}

function isNonEmptyString(value: string | undefined): value is string {
  return typeof value === "string" && value.length > 0;
}

function messageIdentity(message: Message): string | undefined {
  if (
    "tool_call_id" in message &&
    typeof message.tool_call_id === "string" &&
    message.tool_call_id.length > 0
  ) {
    return `tool:${message.tool_call_id}`;
  }
  if (typeof message.id === "string" && message.id.length > 0) {
    return `message:${message.id}`;
  }
  return undefined;
}

function dedupeMessagesByIdentity(messages: Message[]): Message[] {
  const lastIndexByIdentity = new Map<string, number>();

  messages.forEach((message, index) => {
    const identity = messageIdentity(message);
    if (identity) {
      lastIndexByIdentity.set(identity, index);
    }
  });

  return messages.filter((message, index) => {
    const identity = messageIdentity(message);
    return !identity || lastIndexByIdentity.get(identity) === index;
  });
}

function findLatestUnloadedRunIndex(
  runs: Run[],
  loadedRunIds: ReadonlySet<string>,
): number {
  for (let i = runs.length - 1; i >= 0; i--) {
    const run = runs[i];
    if (run && !loadedRunIds.has(run.run_id)) {
      return i;
    }
  }
  return -1;
}

export function mergeMessages(
  historyMessages: Message[],
  threadMessages: Message[],
  optimisticMessages: Message[],
): Message[] {
  const threadMessageIds = new Set(
    threadMessages.map(messageIdentity).filter(isNonEmptyString),
  );

  // The overlap is a contiguous suffix of historyMessages (newest history == oldest thread).
  // Scan from the end: shrink cutoff while messages are already in thread, stop as soon as
  // we hit one that isn't — everything before that point is non-overlapping.
  let cutoff = historyMessages.length;
  for (let i = historyMessages.length - 1; i >= 0; i--) {
    const msg = historyMessages[i];
    if (!msg) {
      continue;
    }
    const identity = messageIdentity(msg);
    if (identity && threadMessageIds.has(identity)) {
      cutoff = i;
    } else {
      break;
    }
  }

  return dedupeMessagesByIdentity([
    ...historyMessages.slice(0, cutoff),
    ...threadMessages,
    ...optimisticMessages,
  ]);
}

function getMessagesAfterBaseline(
  messages: Message[],
  baselineMessageIds: ReadonlySet<string>,
): Message[] {
  return messages.filter((message) => {
    const id = messageIdentity(message);
    return !id || !baselineMessageIds.has(id);
  });
}

export function getVisibleOptimisticMessages(
  optimisticMessages: Message[],
  previousHumanMessageCount: number,
  currentHumanMessageCount: number,
): Message[] {
  if (
    optimisticMessages.some((message) => message.type === "human") &&
    currentHumanMessageCount > previousHumanMessageCount
  ) {
    return [];
  }
  return optimisticMessages;
}

function getStreamErrorMessage(error: unknown): string {
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === "object" && error !== null) {
    const message = Reflect.get(error, "message");
    if (typeof message === "string" && message.trim()) {
      return message;
    }
    const nestedError = Reflect.get(error, "error");
    if (nestedError instanceof Error && nestedError.message.trim()) {
      return nestedError.message;
    }
    if (typeof nestedError === "string" && nestedError.trim()) {
      return nestedError;
    }
  }
  return "Request failed.";
}

const ASYNC_TASK_TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "timeout",
]);

function normalizeAsyncTaskStatus(status: string): string {
  return typeof status === "string" ? status.trim().toLowerCase() : "";
}

function isAsyncTaskTerminalStatus(status: string): boolean {
  const s = normalizeAsyncTaskStatus(status);
  if (ASYNC_TASK_TERMINAL_STATUSES.has(s)) {
    return true;
  }
  return s === "success" || s === "completed";
}

function isAsyncTaskPendingStatus(status: string): boolean {
  const s = normalizeAsyncTaskStatus(status);
  return s === "queued" || s === "running" || s === "awaiting_callback";
}

type AsyncTaskToastChats = {
  asyncTaskToastFailed: string;
  asyncTaskToastSucceeded: string;
  asyncTaskToastCancelled: string;
  asyncTaskToastTimeout: string;
};

function maybeToastAsyncTaskTerminal(
  chats: AsyncTaskToastChats,
  dedupeRef: { current: { key: string; at: number } | null },
  info: {
    taskId: string;
    status: string;
    displayName: string | null;
    taskKind: string;
    error: Record<string, unknown> | null;
    result: Record<string, unknown> | null;
    finishedAt: string | null;
  },
): void {
  const { taskId, status, displayName, taskKind, error, result, finishedAt } =
    info;
  const name = (displayName ?? "").trim() || taskKind;
  const dedupeKey = `${taskId}:${status}:${finishedAt ?? ""}`;
  const now = Date.now();
  const prev = dedupeRef.current;
  if (prev?.key === dedupeKey && now - prev.at < 4000) {
    return;
  }
  dedupeRef.current = { key: dedupeKey, at: now };

  const desc = errorSummaryLine(error) ?? undefined;
  const named = (s: string) => s.replace("{name}", name);
  if (status === "failed") {
    toast.error(
      named(chats.asyncTaskToastFailed),
      desc ? { description: desc } : undefined,
    );
  } else if (status === "succeeded") {
    const note = resultSummaryForToast(result);
    toast.success(
      named(chats.asyncTaskToastSucceeded),
      note ? { description: note } : undefined,
    );
  } else if (status === "cancelled") {
    toast.message(named(chats.asyncTaskToastCancelled));
  } else if (status === "timeout") {
    toast.error(
      named(chats.asyncTaskToastTimeout),
      desc ? { description: desc } : undefined,
    );
  }
}

function mergeAsyncTasksFromApiRows(
  prev: Record<string, ThreadAsyncTaskUiState>,
  rows: ThreadAsyncTaskApiRow[],
  chats: AsyncTaskToastChats,
  dedupeRef: MutableRefObject<{ key: string; at: number } | null>,
): Record<string, ThreadAsyncTaskUiState> {
  const next: Record<string, ThreadAsyncTaskUiState> = {};
  for (const row of rows) {
    next[row.id] = threadAsyncTaskApiRowToUi(row);
  }
  for (const id of Object.keys(next)) {
    const was = prev[id];
    const now = next[id];
    if (!now) {
      continue;
    }
    if (
      was &&
      !isAsyncTaskTerminalStatus(was.status) &&
      isAsyncTaskTerminalStatus(now.status)
    ) {
      const toastStatus = normalizeAsyncTaskStatus(now.status);
      const statusForToast =
        toastStatus === "success" || toastStatus === "completed"
          ? "succeeded"
          : toastStatus;
      maybeToastAsyncTaskTerminal(chats, dedupeRef, {
        taskId: id,
        status: statusForToast,
        displayName: now.displayName,
        taskKind: now.taskKind,
        error: now.error,
        result: now.result,
        finishedAt: now.finishedAt,
      });
    }
  }
  const pendingOnly: Record<string, ThreadAsyncTaskUiState> = {};
  for (const [id, ui] of Object.entries(next)) {
    if (isAsyncTaskPendingStatus(ui.status)) {
      pendingOnly[id] = ui;
    }
  }
  return pendingOnly;
}

export function useThreadStream({
  threadId,
  context,
  isMock,
  langGraphClient,
  onSend,
  onStart,
  onFinish,
  onToolEnd,
}: ThreadStreamOptions) {
  const { t } = useI18n();
  const chatsRef = useRef(t.chats);
  chatsRef.current = t.chats;
  const asyncTerminalToastDedupeRef = useRef<{
    key: string;
    at: number;
  } | null>(null);
  const asyncChaseLastThreadRef = useRef<string | null>(null);
  const asyncChasePrevPendingRef = useRef(false);
  // Track the thread ID that is currently streaming to handle thread changes during streaming
  const [onStreamThreadId, setOnStreamThreadId] = useState(() => threadId);
  // Ref to track current thread ID across async callbacks without causing re-renders,
  // and to allow access to the current thread id in onUpdateEvent
  const threadIdRef = useRef<string | null>(threadId ?? null);
  const startedRef = useRef(false);
  const pendingUsageBaselineMessageIdsRef = useRef<Set<string>>(new Set());

  const listeners = useRef({
    onSend,
    onStart,
    onFinish,
    onToolEnd,
  });

  const {
    messages: history,
    hasMore: hasMoreHistory,
    loadMore: loadMoreHistory,
    loading: isHistoryLoading,
    appendMessages,
  } = useThreadHistory(onStreamThreadId ?? "");

  // Keep listeners ref updated with latest callbacks
  useEffect(() => {
    listeners.current = { onSend, onStart, onFinish, onToolEnd };
  }, [onSend, onStart, onFinish, onToolEnd]);

  useEffect(() => {
    const normalizedThreadId = threadId ?? null;
    if (!normalizedThreadId) {
      // Reset when the UI moves back to a brand new unsaved thread.
      startedRef.current = false;
      setOnStreamThreadId(normalizedThreadId);
    } else {
      setOnStreamThreadId(normalizedThreadId);
    }
    threadIdRef.current = normalizedThreadId;
  }, [threadId]);

  const _handleOnStart = useCallback((id: string) => {
    if (!startedRef.current) {
      listeners.current.onStart?.(id);
      startedRef.current = true;
    }
  }, []);

  const handleStreamStart = useCallback(
    (_threadId: string) => {
      threadIdRef.current = _threadId;
      _handleOnStart(_threadId);
    },
    [_handleOnStart],
  );

  const queryClient = useQueryClient();
  const updateSubtask = useUpdateSubtask();
  const runMetadataStorageRef = useRef<
    ReturnType<typeof getRunMetadataStorage> | undefined
  >(undefined);

  if (
    typeof window !== "undefined" &&
    runMetadataStorageRef.current === undefined
  ) {
    runMetadataStorageRef.current = getRunMetadataStorage();
  }

  const [asyncTasksUi, setAsyncTasksUi] = useState<
    Record<string, ThreadAsyncTaskUiState>
  >({});

  const thread = useStream<AgentThreadState>({
    client: langGraphClient ?? getAPIClient(isMock),
    assistantId: "lead_agent",
    threadId: onStreamThreadId,
    reconnectOnMount: runMetadataStorageRef.current
      ? () => runMetadataStorageRef.current!
      : false,
    fetchStateHistory: { limit: 1 },
    onCreated(meta) {
      handleStreamStart(meta.thread_id);
      setOnStreamThreadId(meta.thread_id);
      const agentMeta =
        context.agent_name ?? context.agent_id;
      if (agentMeta && !isMock) {
        void getAPIClient()
          .threads.update(meta.thread_id, {
            metadata: { agent_name: agentMeta, agent_id: context.agent_id },
          })
          .catch(() => ({}));
      }
    },
    onLangChainEvent(event) {
      if (event.event === "on_tool_end") {
        listeners.current.onToolEnd?.({
          name: event.name,
          data: event.data,
        });
      }
    },
    onUpdateEvent(data) {
      if (data["SummarizationMiddleware.before_model"]) {
        const _messages = [
          ...(data["SummarizationMiddleware.before_model"].messages ?? []),
        ];

        if (_messages.length >= 2) {
          for (const m of _messages) {
            if (m.name === "summary" && m.type === "human") {
              summarizedRef.current?.add(m.id ?? "");
            }
          }
          const _lastKeepMessage = _messages[2];
          const _currentMessages = [...messagesRef.current];
          const _movedMessages: Message[] = [];
          for (const m of _currentMessages) {
            if (m.id !== undefined && m.id === _lastKeepMessage?.id) {
              break;
            }
            if (!summarizedRef.current?.has(m.id ?? "")) {
              _movedMessages.push(m);
            }
          }
          appendMessages(_movedMessages);
          messagesRef.current = [];
        }
      }

      const updates: Array<Partial<AgentThreadState> | null> = Object.values(
        data || {},
      );
      for (const update of updates) {
        if (update && "title" in update && update.title) {
          void queryClient.setQueriesData(
            {
              queryKey: ["threads", "search"],
              exact: false,
            },
            (oldData: Array<AgentThread> | undefined) => {
              return oldData?.map((t) => {
                if (t.thread_id === threadIdRef.current) {
                  return {
                    ...t,
                    values: {
                      ...t.values,
                      title: update.title,
                    },
                  };
                }
                return t;
              });
            },
          );
        }
      }
    },
    onCustomEvent(event: unknown) {
      if (
        typeof event === "object" &&
        event !== null &&
        "type" in event &&
        event.type === "task_running"
      ) {
        const e = event as {
          type: "task_running";
          task_id: string;
          message: AIMessage;
        };
        updateSubtask({ id: e.task_id, latestMessage: e.message });
        return;
      }

      if (
        typeof event === "object" &&
        event !== null &&
        "type" in event &&
        event.type === "llm_retry" &&
        "message" in event &&
        typeof event.message === "string" &&
        event.message.trim()
      ) {
        const e = event as { type: "llm_retry"; message: string };
        toast(e.message);
        return;
      }

      if (
        typeof event === "object" &&
        event !== null &&
        "type" in event &&
        event.type === "async_task_started" &&
        "task_id" in event &&
        typeof (event as { task_id: unknown }).task_id === "string"
      ) {
        const e = event as {
          type: "async_task_started";
          task_id: string;
          task_kind?: string;
        };
        setAsyncTasksUi((prev) => {
          const ex = prev[e.task_id];
          if (ex) {
            return {
              ...prev,
              [e.task_id]: {
                ...ex,
                taskKind: e.task_kind ?? ex.taskKind,
              },
            };
          }
          return {
            ...prev,
            [e.task_id]: {
              taskId: e.task_id,
              taskKind: e.task_kind ?? "task",
              displayName: null,
              externalRef: null,
              status: "queued",
              createdAt: new Date().toISOString(),
              nextPollAt: null,
              finishedAt: null,
              terminalFollowupDone: false,
              pollCommand: null,
              lastPoll: null,
              result: null,
              error: null,
              outcome: null,
            },
          };
        });
      }
    },
    onError(error) {
      setOptimisticMessages([]);
      toast.error(getStreamErrorMessage(error));
      pendingUsageBaselineMessageIdsRef.current = new Set(
        messagesRef.current
          .map(messageIdentity)
          .filter((id): id is string => Boolean(id)),
      );
      if (threadIdRef.current && !isMock) {
        void queryClient.invalidateQueries({
          queryKey: threadTokenUsageQueryKey(threadIdRef.current),
        });
      }
    },
    onFinish(state) {
      const currentThreadId = threadIdRef.current;
      const runId =
        currentThreadId && runMetadataStorageRef.current
          ? runMetadataStorageRef.current.getItem(
              `lg:stream:${currentThreadId}`,
            )
          : null;
      if (currentThreadId && runId) {
        const base = (getBackendBaseURL() ?? "").replace(/\/+$/, "");
        const runUrl = `${base}/api/threads/${encodeURIComponent(currentThreadId)}/runs/${encodeURIComponent(runId)}`;
        void fetch(runUrl, { headers: getAuthHeaders() })
          .then(async (res) => {
            if (!res.ok) {
              return null;
            }
            return (await res.json()) as {
              created_at?: string;
              updated_at?: string;
              metadata?: Record<string, unknown>;
            };
          })
          .then((runData) => {
            if (!runData) {
              return;
            }
            const startedAt =
              typeof runData.created_at === "string"
                ? runData.created_at
                : undefined;
            const metadataFinishedAt = runData.metadata?.finished_at;
            const finishedAt =
              typeof metadataFinishedAt === "string"
                ? metadataFinishedAt
                : typeof runData.updated_at === "string"
                  ? runData.updated_at
                  : undefined;
            const metadataDuration = runData.metadata?.duration_ms;
            let durationMs =
              typeof metadataDuration === "number"
                ? metadataDuration
                : undefined;
            if (durationMs === undefined && startedAt && finishedAt) {
              const startedMs = Date.parse(startedAt);
              const finishedMs = Date.parse(finishedAt);
              if (!Number.isNaN(startedMs) && !Number.isNaN(finishedMs)) {
                durationMs = Math.max(0, finishedMs - startedMs);
              }
            }
            setLastAnswerTiming({
              started_at: startedAt,
              finished_at: finishedAt,
              duration_ms: durationMs,
            });
          })
          .catch(() => undefined);
      } else {
        setLastAnswerTiming({
          finished_at: new Date().toISOString(),
        });
      }
      listeners.current.onFinish?.(state.values);
      pendingUsageBaselineMessageIdsRef.current = new Set(
        messagesRef.current
          .map(messageIdentity)
          .filter((id): id is string => Boolean(id)),
      );
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
      if (threadIdRef.current && !isMock) {
        void queryClient.invalidateQueries({
          queryKey: threadTokenUsageQueryKey(threadIdRef.current),
        });
      }
    },
  });

  const threadStreamRef = useRef(thread);
  threadStreamRef.current = thread;
  const streamLoadingRef = useRef(false);
  streamLoadingRef.current = thread.isLoading;

  const joinOpts = useMemo(
    () => ({ isStreamLoading: () => streamLoadingRef.current }),
    [],
  );

  const scheduleJoinActiveRun = useCallback(
    (tid: string) => {
      if (!runMetadataStorageRef.current) {
        return;
      }
      const join = (
        threadStreamRef.current as {
          joinStream?: (
            runId: string,
            lastEventId?: string,
          ) => Promise<unknown>;
        }
      ).joinStream;
      if (typeof join !== "function") {
        return;
      }
      const ac = new AbortController();
      void joinActiveRunIfStaleOrMissing(
        tid,
        runMetadataStorageRef.current,
        join,
        ac.signal,
        joinOpts,
      );
    },
    [joinOpts],
  );

  // Opening a chat in a new tab has no `lg:stream:${threadId}` in sessionStorage, so the SDK
  // will not call joinStream; only checkpoint history refreshes until manual reload. If the
  // gateway still has an in-flight run for this thread, attach to its SSE here.
  useEffect(() => {
    if (isMock || !threadId || !runMetadataStorageRef.current) {
      return;
    }
    const storage = runMetadataStorageRef.current;
    const join = (
      threadStreamRef.current as {
        joinStream?: (runId: string, lastEventId?: string) => Promise<unknown>;
      }
    ).joinStream;
    if (typeof join !== "function") {
      return;
    }
    const ac = new AbortController();
    void joinActiveRunIfStaleOrMissing(threadId, storage, join, ac.signal);
    return () => {
      ac.abort();
    };
  }, [threadId, isMock]);

  useEffect(() => {
    if (isMock || !threadId || !runMetadataStorageRef.current) {
      return;
    }
    const storage = runMetadataStorageRef.current;
    let cancelled = false;
    const onVisibility = () => {
      if (document.visibilityState !== "visible" || cancelled) {
        return;
      }
      const tid = threadIdRef.current;
      if (!tid || tid !== threadId) {
        return;
      }
      void fetchThreadAsyncTasks(tid).then((rows) => {
        if (cancelled || rows === null) {
          return;
        }
        setAsyncTasksUi((prev) =>
          mergeAsyncTasksFromApiRows(
            prev,
            rows,
            chatsRef.current,
            asyncTerminalToastDedupeRef,
          ),
        );
        queueMicrotask(() => {
          if (!cancelled) {
            scheduleJoinActiveRun(tid);
          }
        });
      });
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [threadId, isMock, scheduleJoinActiveRun]);

  useEffect(() => {
    if (isMock || !threadId || !runMetadataStorageRef.current) {
      return;
    }
    let cancelled = false;
    const onOnline = () => {
      const tid = threadIdRef.current;
      if (!tid || tid !== threadId || cancelled) {
        return;
      }
      void fetchThreadAsyncTasks(tid).then((rows) => {
        if (cancelled || rows === null) {
          return;
        }
        setAsyncTasksUi((prev) =>
          mergeAsyncTasksFromApiRows(
            prev,
            rows,
            chatsRef.current,
            asyncTerminalToastDedupeRef,
          ),
        );
        queueMicrotask(() => {
          if (!cancelled) {
            scheduleJoinActiveRun(tid);
          }
        });
      });
    };
    window.addEventListener("online", onOnline);
    return () => {
      cancelled = true;
      window.removeEventListener("online", onOnline);
    };
  }, [threadId, isMock, scheduleJoinActiveRun]);

  const asyncTaskUiPollMs = env.NEXT_PUBLIC_ASYNC_TASK_UI_POLL_MS ?? 45_000;

  /** Only queued / running / awaiting_callback need periodic GET; terminal rows do not. */
  const hasPendingAsyncTaskUi = useMemo(
    () =>
      Object.values(asyncTasksUi).some((row) =>
        isAsyncTaskPendingStatus(row.status),
      ),
    [asyncTasksUi],
  );

  const asyncTaskUiPollIntervalMs = useMemo(() => {
    if (!hasPendingAsyncTaskUi) {
      return 0;
    }
    if (asyncTaskUiPollMs <= 0) {
      return 5000;
    }
    return Math.min(asyncTaskUiPollMs, 5000);
  }, [asyncTaskUiPollMs, hasPendingAsyncTaskUi]);

  // While there is at least one non-terminal async_task in local UI, periodically refresh + try join(active run).
  // No interval when every card is terminal (succeeded / failed / …) or there are no cards yet (initial fetch is elsewhere).
  useEffect(() => {
    if (isMock || !threadId || typeof window === "undefined") {
      return;
    }
    if (asyncTaskUiPollIntervalMs <= 0) {
      return;
    }
    const tick = () => {
      if (document.visibilityState !== "visible") {
        return;
      }
      const tid = threadIdRef.current;
      if (!tid || tid !== threadId) {
        return;
      }
      void fetchThreadAsyncTasks(tid).then((rows) => {
        if (rows === null) {
          return;
        }
        setAsyncTasksUi((prev) =>
          mergeAsyncTasksFromApiRows(
            prev,
            rows,
            chatsRef.current,
            asyncTerminalToastDedupeRef,
          ),
        );
        queueMicrotask(() => {
          scheduleJoinActiveRun(tid);
        });
      });
    };
    const id = window.setInterval(tick, asyncTaskUiPollIntervalMs);
    return () => {
      window.clearInterval(id);
    };
  }, [threadId, isMock, scheduleJoinActiveRun, asyncTaskUiPollIntervalMs]);

  // Last poll often sees terminal status and stops the interval before the gateway registers the
  // terminal follow-up run. Re-fetch + join a few times when pending → all-terminal.
  useEffect(() => {
    if (isMock || !threadId || typeof window === "undefined") {
      asyncChaseLastThreadRef.current = null;
      return;
    }
    if (asyncChaseLastThreadRef.current !== threadId) {
      asyncChaseLastThreadRef.current = threadId;
      asyncChasePrevPendingRef.current = hasPendingAsyncTaskUi;
      return;
    }
    const wasPending = asyncChasePrevPendingRef.current;
    asyncChasePrevPendingRef.current = hasPendingAsyncTaskUi;
    if (hasPendingAsyncTaskUi || !wasPending) {
      return;
    }
    const tid = threadId;
    const delays = [0, 800, 2200];
    const ids = delays.map((delay) =>
      window.setTimeout(() => {
        if (threadIdRef.current !== tid) {
          return;
        }
        void fetchThreadAsyncTasks(tid).then((rows) => {
          if (rows === null || threadIdRef.current !== tid) {
            return;
          }
          setAsyncTasksUi((prev) =>
            mergeAsyncTasksFromApiRows(
              prev,
              rows,
              chatsRef.current,
              asyncTerminalToastDedupeRef,
            ),
          );
          queueMicrotask(() => {
            if (threadIdRef.current === tid) {
              scheduleJoinActiveRun(tid);
            }
          });
        });
      }, delay),
    );
    return () => {
      for (const id of ids) {
        window.clearTimeout(id);
      }
    };
  }, [threadId, hasPendingAsyncTaskUi, isMock, scheduleJoinActiveRun]);

  const asyncTaskProgressMessages = useMemo((): Message[] => {
    const list = Object.values(asyncTasksUi);
    list.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    return list.map((row) =>
      createAsyncTaskProgressMessage(
        `async-task-ui-${row.taskId}`,
        formatAsyncTaskMarkdown(row, t.chats),
      ),
    );
  }, [asyncTasksUi, t.chats]);

  // Optimistic messages shown before the server stream responds
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [lastAnswerTiming, setLastAnswerTiming] =
    useState<RunEndPayload | null>(null);
  const humanMessageCount = thread.messages.filter(
    (m) => m.type === "human",
  ).length;
  const latestMessageCountsRef = useRef({ humanMessageCount });
  const sendInFlightRef = useRef(false);
  const messagesRef = useRef<Message[]>([]);
  const summarizedRef = useRef<Set<string>>(null);
  const prevHumanMsgCountRef = useRef(humanMessageCount);

  latestMessageCountsRef.current = { humanMessageCount };
  summarizedRef.current ??= new Set<string>();

  // Reset thread-local pending UI state when switching between threads so
  // optimistic messages and in-flight guards do not leak across chat views.
  useEffect(() => {
    startedRef.current = false;
    sendInFlightRef.current = false;
    pendingUsageBaselineMessageIdsRef.current = new Set(
      messagesRef.current
        .map(messageIdentity)
        .filter((id): id is string => Boolean(id)),
    );
    prevHumanMsgCountRef.current =
      latestMessageCountsRef.current.humanMessageCount;
    setOptimisticMessages([]);
    setAsyncTasksUi({});
    setIsUploading(false);
    setLastAnswerTiming(null);
  }, [threadId]);

  useEffect(() => {
    if (
      thread.isLoading &&
      pendingUsageBaselineMessageIdsRef.current.size === 0
    ) {
      pendingUsageBaselineMessageIdsRef.current = new Set(
        thread.messages
          .map(messageIdentity)
          .filter((id): id is string => Boolean(id)),
      );
    }
  }, [thread.isLoading, thread.messages]);

  useEffect(() => {
    if (isMock || !threadId) {
      return;
    }
    const ac = new AbortController();
    void fetchThreadAsyncTasks(threadId).then((rows) => {
      if (ac.signal.aborted || rows === null) {
        return;
      }
      setAsyncTasksUi((prev) =>
        mergeAsyncTasksFromApiRows(
          prev,
          rows,
          chatsRef.current,
          asyncTerminalToastDedupeRef,
        ),
      );
      queueMicrotask(() => {
        if (!ac.signal.aborted) {
          scheduleJoinActiveRun(threadId);
        }
      });
    });
    return () => ac.abort();
  }, [threadId, isMock, scheduleJoinActiveRun]);

  // Thread-level async_task SSE removed: task cards refresh via GET + visibility (see plan).

  const optimisticMessageCount = optimisticMessages.length;
  const hasHumanOptimistic = optimisticMessages.some((m) => m.type === "human");
  useEffect(() => {
    if (optimisticMessageCount === 0) return;

    const newHumanMsgArrived = humanMessageCount > prevHumanMsgCountRef.current;

    if (!hasHumanOptimistic || newHumanMsgArrived) {
      setOptimisticMessages([]);
    }
  }, [hasHumanOptimistic, humanMessageCount, optimisticMessageCount]);

  useEffect(() => {
    const activeThreadId = threadIdRef.current;
    if (!activeThreadId) {
      return;
    }

    const controller = new AbortController();
    const base = (getBackendBaseURL() ?? "").replace(/\/+$/, "");
    const runsUrl = `${base}/api/threads/${encodeURIComponent(activeThreadId)}/runs`;

    void fetch(runsUrl, {
      headers: getAuthHeaders(),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          return [];
        }
        return (await res.json()) as Array<{
          created_at?: string;
          updated_at?: string;
          metadata?: Record<string, unknown>;
          status?: string;
        }>;
      })
      .then((runs) => {
        if (!Array.isArray(runs) || runs.length === 0) {
          return;
        }
        const latestFinishedRun = runs.find(
          (run) => run.status === "success" || run.status === "error",
        );
        if (!latestFinishedRun) {
          return;
        }
        const startedAt =
          typeof latestFinishedRun.created_at === "string"
            ? latestFinishedRun.created_at
            : undefined;
        const metadataFinishedAt = latestFinishedRun.metadata?.finished_at;
        const finishedAt =
          typeof metadataFinishedAt === "string"
            ? metadataFinishedAt
            : typeof latestFinishedRun.updated_at === "string"
              ? latestFinishedRun.updated_at
              : undefined;
        const metadataDuration = latestFinishedRun.metadata?.duration_ms;
        let durationMs =
          typeof metadataDuration === "number" ? metadataDuration : undefined;
        if (durationMs === undefined && startedAt && finishedAt) {
          const startedMs = Date.parse(startedAt);
          const finishedMs = Date.parse(finishedAt);
          if (!Number.isNaN(startedMs) && !Number.isNaN(finishedMs)) {
            durationMs = Math.max(0, finishedMs - startedMs);
          }
        }
        if (finishedAt) {
          setLastAnswerTiming({
            started_at: startedAt,
            finished_at: finishedAt,
            duration_ms: durationMs,
          });
        }
      })
      .catch(() => undefined);

    return () => controller.abort();
  }, [threadId]);

  const sendMessage = useCallback(
    async (
      threadId: string,
      message: PromptInputMessage,
      extraContext?: Record<string, unknown>,
      options?: SendMessageOptions,
    ) => {
      if (sendInFlightRef.current) {
        return;
      }
      sendInFlightRef.current = true;

      const text = message.text.trim();

      listeners.current.onSend?.(threadId);

      prevHumanMsgCountRef.current = humanMessageCount;
      pendingUsageBaselineMessageIdsRef.current = new Set(
        thread.messages
          .map(messageIdentity)
          .filter((id): id is string => Boolean(id)),
      );

      setAsyncTasksUi({});

      const activeAsyncTaskThreadId = () => threadIdRef.current ?? threadId;
      const syncAsyncTasksFromApi = () => {
        const tid = activeAsyncTaskThreadId();
        if (isMock || !tid) {
          return;
        }
        void fetchThreadAsyncTasks(tid).then((rows) => {
          if (!rows) {
            return;
          }
          setAsyncTasksUi((prev) =>
            mergeAsyncTasksFromApiRows(
              prev,
              rows,
              chatsRef.current,
              asyncTerminalToastDedupeRef,
            ),
          );
          queueMicrotask(() => {
            scheduleJoinActiveRun(tid);
          });
        });
      };

      // Build optimistic files list with uploading status
      const optimisticFiles: FileInMessage[] = (message.files ?? []).map(
        (f) => ({
          filename: f.filename ?? "",
          size: 0,
          status: "uploading" as const,
        }),
      );

      const hideFromUI = options?.additionalKwargs?.hide_from_ui === true;
      const optimisticAdditionalKwargs = {
        ...options?.additionalKwargs,
        ...(optimisticFiles.length > 0 ? { files: optimisticFiles } : {}),
      };

      const newOptimistic: Message[] = [];
      if (!hideFromUI) {
        newOptimistic.push({
          type: "human",
          id: `opt-human-${Date.now()}`,
          content: text ? [{ type: "text", text }] : "",
          additional_kwargs: optimisticAdditionalKwargs,
        });
      }

      if (optimisticFiles.length > 0 && !hideFromUI) {
        // Mock AI message while files are being uploaded
        newOptimistic.push({
          type: "ai",
          id: `opt-ai-${Date.now()}`,
          content: t.uploads.uploadingFiles,
          additional_kwargs: { element: "task" },
        });
      }
      setOptimisticMessages(newOptimistic);

      // Only fire onStart immediately for an existing persisted thread.
      // Brand-new chats should wait for onCreated(meta.thread_id) so URL sync
      // uses the real server-generated thread id.
      if (threadIdRef.current) {
        _handleOnStart(threadId);
      }

      let uploadedFileInfo: UploadedFileInfo[] = [];

      try {
        // Upload files first if any
        if (message.files && message.files.length > 0) {
          setIsUploading(true);
          try {
            const filePromises = message.files.map((fileUIPart) =>
              promptInputFilePartToFile(fileUIPart),
            );

            const conversionResults = await Promise.all(filePromises);
            const files = conversionResults.filter(
              (file): file is File => file !== null,
            );
            const failedConversions = conversionResults.length - files.length;

            if (failedConversions > 0) {
              throw new Error(
                `Failed to prepare ${failedConversions} attachment(s) for upload. Please retry.`,
              );
            }

            if (!threadId) {
              throw new Error("Thread is not ready for file upload.");
            }

            if (files.length > 0) {
              const uploadResponse = await uploadFiles(threadId, files);
              uploadedFileInfo = uploadResponse.files;

              // Update optimistic human message with uploaded status + paths
              const uploadedFiles: FileInMessage[] = uploadedFileInfo.map(
                (info) => ({
                  filename: info.filename,
                  size: info.size,
                  path: info.virtual_path,
                  status: "uploaded" as const,
                }),
              );
              setOptimisticMessages((messages) => {
                if (messages.length > 1 && messages[0]) {
                  const humanMessage: Message = messages[0];
                  return [
                    {
                      ...humanMessage,
                      additional_kwargs: { files: uploadedFiles },
                    },
                    ...messages.slice(1),
                  ];
                }
                return messages;
              });
            }
          } catch (error) {
            const errorMessage =
              error instanceof Error
                ? error.message
                : "Failed to upload files.";
            toast.error(errorMessage);
            setOptimisticMessages([]);
            throw error;
          } finally {
            setIsUploading(false);
          }
        }

        // Build files metadata for submission (included in additional_kwargs)
        const filesForSubmit: FileInMessage[] = uploadedFileInfo.map(
          (info) => ({
            filename: info.filename,
            size: info.size,
            path: info.virtual_path,
            status: "uploaded" as const,
          }),
        );

        const token = getToken();
        const deerflowUserId = getJwtSubject();
        await thread.submit(
          {
            messages: [
              {
                type: "human",
                content: [
                  {
                    type: "text",
                    text,
                  },
                ],
                additional_kwargs: {
                  client_sent_at: new Date().toISOString(),
                  ...options?.additionalKwargs,
                  ...(filesForSubmit.length > 0
                    ? { files: filesForSubmit }
                    : {}),
                },
              },
            ],
          },
          {
            threadId: threadId,
            streamSubgraphs: true,
            streamResumable: true,
            config: {
              recursion_limit: 1000,
            },
            context: {
              ...context,
              ...extraContext,
              thinking_enabled: context.mode !== "flash",
              is_plan_mode: context.mode === "pro" || context.mode === "ultra",
              subagent_enabled: context.mode === "ultra",
              reasoning_effort:
                context.reasoning_effort ??
                (context.mode === "ultra"
                  ? "high"
                  : context.mode === "pro"
                    ? "medium"
                    : context.mode === "thinking"
                      ? "low"
                      : undefined),
              thread_id: threadId,
              ...(!token && deerflowUserId ? { user_id: deerflowUserId } : {}),
            },
          },
        );
        void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
        syncAsyncTasksFromApi();
      } catch (error) {
        setOptimisticMessages([]);
        setIsUploading(false);
        syncAsyncTasksFromApi();
        throw error;
      } finally {
        sendInFlightRef.current = false;
      }
    },
    [
      thread,
      _handleOnStart,
      t.uploads.uploadingFiles,
      context,
      queryClient,
      isMock,
      scheduleJoinActiveRun,
      humanMessageCount,
    ],
  );

  if (thread.messages.length >= messagesRef.current.length) {
    messagesRef.current = thread.messages;
  }

  const visibleOptimisticMessages = getVisibleOptimisticMessages(
    optimisticMessages,
    prevHumanMsgCountRef.current,
    humanMessageCount,
  );

  const mergedMessages = mergeMessages(
    history,
    thread.messages,
    visibleOptimisticMessages,
  );
  const displayMessages =
    asyncTaskProgressMessages.length > 0
      ? [...mergedMessages, ...asyncTaskProgressMessages]
      : mergedMessages;

  const pendingUsageMessages = thread.isLoading
    ? getMessagesAfterBaseline(
        thread.messages,
        pendingUsageBaselineMessageIdsRef.current,
      )
    : [];

  const mergedValues: AgentThreadState = {
    ...thread.values,
    __answer_timing: lastAnswerTiming,
  };

  const mergedThread = {
    ...thread,
    messages: displayMessages,
    values: mergedValues,
  } as typeof thread;

  return {
    thread: mergedThread,
    pendingUsageMessages,
    sendMessage,
    isUploading,
    isHistoryLoading,
    hasMoreHistory,
    loadMoreHistory,
  } as const;
}

export function useThreads(
  params: Parameters<ThreadsClient["search"]>[0] = {
    limit: 50,
    sortBy: "updated_at",
    sortOrder: "desc",
    select: ["thread_id", "updated_at", "values", "metadata"],
  },
) {
  const apiClient = getAPIClient();
  const isStaticDemo = env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true";
  const hasAuthToken = Boolean(getToken());

  return useQuery<AgentThread[]>({
    queryKey: ["threads", "search", params, isStaticDemo, hasAuthToken],
    queryFn: async () => {
      if (!isStaticDemo) {
        return searchThreadsViaGateway(params);
      }

      const maxResults = params.limit;
      const initialOffset = params.offset ?? 0;
      const DEFAULT_PAGE_SIZE = 50;

      // Preserve prior semantics: if a non-positive limit is explicitly provided,
      // delegate to a single search call with the original parameters.
      if (maxResults !== undefined && maxResults <= 0) {
        const response =
          await apiClient.threads.search<AgentThreadState>(params);
        return response as AgentThread[];
      }

      const pageSize =
        typeof maxResults === "number" && maxResults > 0
          ? Math.min(DEFAULT_PAGE_SIZE, maxResults)
          : DEFAULT_PAGE_SIZE;

      const threads: AgentThread[] = [];
      let offset = initialOffset;

      while (true) {
        if (typeof maxResults === "number" && threads.length >= maxResults) {
          break;
        }

        const currentLimit =
          typeof maxResults === "number"
            ? Math.min(pageSize, maxResults - threads.length)
            : pageSize;

        if (typeof maxResults === "number" && currentLimit <= 0) {
          break;
        }

        const response = (await apiClient.threads.search<AgentThreadState>({
          ...params,
          limit: currentLimit,
          offset,
        })) as AgentThread[];

        threads.push(...response);

        if (response.length < currentLimit) {
          break;
        }

        offset += response.length;
      }

      return threads;
    },
    refetchOnWindowFocus: false,
  });
}

export function useThreadRuns(threadId?: string) {
  const apiClient = getAPIClient();
  return useQuery<Run[]>({
    queryKey: ["thread", threadId],
    queryFn: async () => {
      if (!threadId) {
        return [];
      }
      const response = await apiClient.runs.list(threadId);
      return response;
    },
    refetchOnWindowFocus: false,
  });
}

export function useThreadTokenUsage(
  threadId?: string | null,
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery<ThreadTokenUsageResponse | null>({
    queryKey: threadTokenUsageQueryKey(threadId),
    queryFn: async () => {
      if (!threadId) {
        return null;
      }
      return fetchThreadTokenUsage(threadId);
    },
    enabled: enabled && Boolean(threadId),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useRunDetail(threadId: string, runId: string) {
  const apiClient = getAPIClient();
  return useQuery<Run>({
    queryKey: ["thread", threadId, "run", runId],
    queryFn: async () => {
      const response = await apiClient.runs.get(threadId, runId);
      return response;
    },
    refetchOnWindowFocus: false,
  });
}

export function useThreadHistory(threadId: string) {
  const runs = useThreadRuns(threadId);
  const threadIdRef = useRef(threadId);
  const runsRef = useRef(runs.data ?? []);
  const indexRef = useRef(-1);
  const loadingRef = useRef(false);
  const pendingLoadRef = useRef(false);
  const loadingRunIdRef = useRef<string | null>(null);
  const loadedRunIdsRef = useRef<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);

  const loadMessages = useCallback(async () => {
    if (loadingRef.current) {
      const pendingRunIndex = findLatestUnloadedRunIndex(
        runsRef.current,
        loadedRunIdsRef.current,
      );
      const pendingRun = runsRef.current[pendingRunIndex];
      if (pendingRun && pendingRun.run_id !== loadingRunIdRef.current) {
        pendingLoadRef.current = true;
      }
      return;
    }
    if (runsRef.current.length === 0) {
      return;
    }

    loadingRef.current = true;
    setLoading(true);

    try {
      do {
        pendingLoadRef.current = false;

        const nextRunIndex = findLatestUnloadedRunIndex(
          runsRef.current,
          loadedRunIdsRef.current,
        );
        indexRef.current = nextRunIndex;

        const run = runsRef.current[nextRunIndex];
        if (!run) {
          indexRef.current = -1;
          return;
        }

        const requestThreadId = threadIdRef.current;
        loadingRunIdRef.current = run.run_id;
        const result: { data: RunMessage[]; hasMore: boolean } = await fetch(
          `${getBackendBaseURL()}/api/threads/${encodeURIComponent(requestThreadId)}/runs/${encodeURIComponent(run.run_id)}/messages`,
          {
            method: "GET",
            headers: {
              "Content-Type": "application/json",
            },
            credentials: "include",
          },
        ).then((res) => {
          return res.json();
        });
        const _messages = result.data
          .filter((m) => !m.metadata.caller?.startsWith("middleware:"))
          .map((m) => m.content);
        if (threadIdRef.current !== requestThreadId) {
          return;
        }
        setMessages((prev) =>
          dedupeMessagesByIdentity([..._messages, ...prev]),
        );
        loadedRunIdsRef.current.add(run.run_id);
        indexRef.current = findLatestUnloadedRunIndex(
          runsRef.current,
          loadedRunIdsRef.current,
        );
      } while (pendingLoadRef.current);
    } catch (err) {
      console.error(err);
    } finally {
      loadingRef.current = false;
      loadingRunIdRef.current = null;
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const threadChanged = threadIdRef.current !== threadId;
    threadIdRef.current = threadId;

    if (threadChanged) {
      runsRef.current = [];
      indexRef.current = -1;
      pendingLoadRef.current = false;
      loadingRunIdRef.current = null;
      loadedRunIdsRef.current = new Set();
      loadingRef.current = false;
      setLoading(false);
      setMessages([]);
    }

    if (runs.data && runs.data.length > 0) {
      runsRef.current = runs.data ?? [];
      indexRef.current = findLatestUnloadedRunIndex(
        runs.data,
        loadedRunIdsRef.current,
      );
    }
    loadMessages().catch(() => {
      toast.error("Failed to load thread history.");
    });
  }, [threadId, runs.data, loadMessages]);

  const appendMessages = useCallback((_messages: Message[]) => {
    setMessages((prev) => {
      return dedupeMessagesByIdentity([...prev, ..._messages]);
    });
  }, []);
  const hasMore = indexRef.current >= 0 || !runs.data;
  return {
    runs: runs.data,
    messages,
    loading,
    appendMessages,
    hasMore,
    loadMore: loadMessages,
  };
}


export function useDeleteThread() {
  const queryClient = useQueryClient();
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({ threadId }: { threadId: string }) => {
      await apiClient.threads.delete(threadId);

      const response = await fetch(
        `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}`,
        {
          method: "DELETE",
          headers: getAuthHeaders(),
        },
      );

      if (!response.ok) {
        const error = await response
          .json()
          .catch(() => ({ detail: "Failed to delete local thread data." }));
        throw new Error(error.detail ?? "Failed to delete local thread data.");
      }
    },
    onSuccess(_, { threadId }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread> | undefined) => {
          if (oldData == null) {
            return oldData;
          }
          return oldData.filter((t) => t.thread_id !== threadId);
        },
      );
    },
    onSettled() {
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
    },
  });
}

export function useRenameThread() {
  const queryClient = useQueryClient();
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({
      threadId,
      title,
    }: {
      threadId: string;
      title: string;
    }) => {
      await apiClient.threads.updateState(threadId, {
        values: { title },
      });
    },
    onSuccess(_, { threadId, title }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread>) => {
          return oldData.map((t) => {
            if (t.thread_id === threadId) {
              return {
                ...t,
                values: {
                  ...t.values,
                  title,
                },
              };
            }
            return t;
          });
        },
      );
    },
  });
}

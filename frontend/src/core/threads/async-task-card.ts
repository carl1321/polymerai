import type { ThreadAsyncTaskApiRow } from "../api/async-tasks";
import type { Translations } from "../i18n/locales/types";

export type ThreadAsyncTaskUiState = {
  taskId: string;
  taskKind: string;
  displayName: string | null;
  externalRef: string | null;
  status: string;
  createdAt: string;
  nextPollAt: string | null;
  finishedAt: string | null;
  terminalFollowupDone: boolean;
  pollCommand: string | null;
  lastPoll: Record<string, unknown> | null;
  /** From API for terminal rows; used by terminal toast (succeeded summary), not by card when pending-only. */
  result: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  outcome: string | null;
};

function lastPollFromPayload(
  payload: Record<string, unknown>,
): Record<string, unknown> | null {
  const lp = payload.last_poll;
  if (lp && typeof lp === "object" && !Array.isArray(lp)) {
    return lp as Record<string, unknown>;
  }
  return null;
}

function formatLocalDateTime(iso: string | null): string | null {
  if (!iso?.trim()) {
    return null;
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return null;
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatLastPollPlain(last: Record<string, unknown>): string {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(last)) {
    if (v === null || v === undefined) {
      continue;
    }
    if (typeof v === "object") {
      try {
        lines.push(`- **${k}:** ${JSON.stringify(v)}`);
      } catch {
        lines.push(`- **${k}:** …`);
      }
    } else if (
      typeof v === "string" ||
      typeof v === "number" ||
      typeof v === "boolean" ||
      typeof v === "bigint"
    ) {
      lines.push(`- **${k}:** ${v}`);
    }
  }
  return lines.join("\n");
}

function isScalarPollField(v: unknown): boolean {
  return v !== null && v !== undefined && typeof v !== "object";
}

/** Drop ``status`` when it duplicates ``job_state`` (same meaning, different casing). */
function dedupeLastPollFields(
  last: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...last };
  const st = out.status;
  const js = out.job_state;
  if (
    isScalarPollField(st) &&
    isScalarPollField(js) &&
    String(st).trim().toLowerCase() === String(js).trim().toLowerCase()
  ) {
    delete out.status;
  }
  return out;
}

function lastPollDisplayBody(
  last: Record<string, unknown> | null,
): string | null {
  if (!last || Object.keys(last).length === 0) {
    return null;
  }
  const body = formatLastPollPlain(dedupeLastPollFields(last)).trim();
  return body !== "" ? body : null;
}

export function errorSummaryLine(
  err: Record<string, unknown> | null,
): string | null {
  if (!err || Object.keys(err).length === 0) {
    return null;
  }
  const m = Reflect.get(err, "message");
  if (typeof m === "string" && m.trim()) {
    const base = m.trim();
    const det = Reflect.get(err, "details");
    if (det && typeof det === "object" && det !== null) {
      const errors = Reflect.get(det, "errors");
      if (
        Array.isArray(errors) &&
        errors.length > 0 &&
        typeof errors[0] === "string"
      ) {
        const e0 = errors[0].trim();
        if (e0 && !base.includes(e0)) {
          return `${base}（${e0}）`;
        }
      }
    }
    return base;
  }
  const c = Reflect.get(err, "code");
  if (typeof c === "string" && c.trim()) {
    return c.trim();
  }
  return null;
}

export function resultSummaryForToast(
  result: Record<string, unknown> | null,
): string | undefined {
  if (!result || Object.keys(result).length === 0) {
    return undefined;
  }
  const bits: string[] = [];
  const topErr = Reflect.get(result, "errors");
  if (
    Array.isArray(topErr) &&
    topErr.length > 0 &&
    typeof topErr[0] === "string" &&
    topErr[0].trim()
  ) {
    bits.push(topErr[0].trim());
  }
  const det = Reflect.get(result, "details");
  if (det && typeof det === "object" && det !== null) {
    const de = Reflect.get(det, "errors");
    if (
      Array.isArray(de) &&
      de.length > 0 &&
      typeof de[0] === "string" &&
      de[0].trim()
    ) {
      const line = de[0].trim();
      if (!bits.some((b) => b.includes(line))) {
        bits.push(line);
      }
    }
  }
  if (Reflect.get(result, "converged") === false) {
    bits.push("未报告完全收敛");
  }
  const fe = Reflect.get(result, "final_energy_eV");
  if (typeof fe === "number") {
    bits.push(`报告末态能量 ${fe} eV`);
  } else if (typeof fe === "string" && fe.trim() !== "") {
    bits.push(`报告末态能量 ${fe.trim()} eV`);
  }
  if (bits.length === 0) {
    return undefined;
  }
  return bits.join("；");
}

export function threadAsyncTaskApiRowToUi(
  row: ThreadAsyncTaskApiRow,
): ThreadAsyncTaskUiState {
  const st = row.status;
  const outcome =
    st === "succeeded" ||
    st === "failed" ||
    st === "cancelled" ||
    st === "timeout"
      ? st
      : null;
  return {
    taskId: row.id,
    taskKind: row.task_kind,
    displayName: row.display_name,
    externalRef: row.external_ref,
    status: row.status,
    createdAt: row.created_at,
    nextPollAt: row.next_poll_at,
    finishedAt: row.finished_at,
    terminalFollowupDone: row.terminal_followup_done,
    pollCommand: null,
    lastPoll: lastPollFromPayload(row.payload ?? {}),
    result: row.result,
    error: row.error,
    outcome,
  };
}

function normalizeStatus(status: string): string {
  return typeof status === "string" ? status.trim().toLowerCase() : "";
}

function statusLabel(status: string, chats: Translations["chats"]): string {
  const s = normalizeStatus(status);
  switch (s) {
    case "queued":
      return chats.asyncTaskStatusQueued;
    case "running":
      return chats.asyncTaskStatusRunning;
    case "awaiting_callback":
      return chats.asyncTaskStatusAwaitingCallback;
    case "succeeded":
    case "success":
    case "completed":
      return chats.asyncTaskStatusSucceeded;
    case "failed":
      return chats.asyncTaskStatusFailed;
    case "cancelled":
      return chats.asyncTaskStatusCancelled;
    case "timeout":
      return chats.asyncTaskStatusTimeout;
    default:
      return status;
  }
}

export function formatAsyncTaskMarkdown(
  row: ThreadAsyncTaskUiState,
  chats: Translations["chats"],
): string {
  const dn = row.displayName?.trim() ?? "";
  const name = dn !== "" ? dn : row.taskKind;
  const lines = [
    `### ${chats.asyncTaskProgressTitle}`,
    "",
    `- **${chats.asyncTaskFieldName}:** ${name}`,
    `- **${chats.asyncTaskFieldStatus}:** ${statusLabel(row.status, chats)}`,
  ];
  const ref = row.externalRef?.trim();
  if (ref) {
    lines.push(`- **${chats.asyncTaskFieldRef}:** \`${ref}\``);
  }
  if (normalizeStatus(row.status) === "failed") {
    const summary = errorSummaryLine(row.error);
    if (summary) {
      lines.push(`- **${chats.asyncTaskErrorHeading}:** ${summary}`);
    }
  }

  const nextFmt = formatLocalDateTime(row.nextPollAt);
  const lastBody = lastPollDisplayBody(row.lastPoll);

  if (lastBody) {
    lines.push("", `**${chats.asyncTaskLastPollHeading}**`, "", lastBody);
    if (nextFmt) {
      lines.push("", `- **${chats.asyncTaskFieldNextPoll}:** ${nextFmt}`);
    }
  } else if (nextFmt) {
    lines.push("", `- **${chats.asyncTaskFieldNextPoll}:** ${nextFmt}`);
  }

  return lines.join("\n");
}

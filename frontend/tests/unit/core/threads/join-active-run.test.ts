import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/core/config", () => ({
  getBackendBaseURL: () => "http://test.local",
}));

vi.mock("@/core/auth/token", () => ({
  getAuthHeaders: () => ({}),
}));

import { joinActiveRunIfStaleOrMissing } from "@/core/threads/join-active-run";

describe("joinActiveRunIfStaleOrMissing", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [{ run_id: "run-active", status: "running" }],
      } as Response),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("joins when session run id differs from active run", async () => {
    const join = vi.fn().mockResolvedValue(undefined);
    const storage = { getItem: vi.fn().mockReturnValue("run-old") };
    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
    );
    expect(join).toHaveBeenCalledWith("run-active");
  });

  it("does not join when same run id and isStreamLoading is not false", async () => {
    const join = vi.fn();
    const storage = { getItem: vi.fn().mockReturnValue("run-active") };
    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
    );
    expect(join).not.toHaveBeenCalled();

    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
      { isStreamLoading: true },
    );
    expect(join).not.toHaveBeenCalled();
  });

  it("joins when same run id and isStreamLoading is false", async () => {
    const join = vi.fn().mockResolvedValue(undefined);
    const storage = { getItem: vi.fn().mockReturnValue("run-active") };
    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
      { isStreamLoading: false },
    );
    expect(join).toHaveBeenCalledWith("run-active");
  });

  it("joins when same run id and isStreamLoading callback returns false", async () => {
    const join = vi.fn().mockResolvedValue(undefined);
    const storage = { getItem: vi.fn().mockReturnValue("run-active") };
    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
      { isStreamLoading: () => false },
    );
    expect(join).toHaveBeenCalledWith("run-active");
  });

  it("returns without join when no active run", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [{ run_id: "r1", status: "success" }],
    } as Response);
    const join = vi.fn();
    const storage = { getItem: vi.fn().mockReturnValue(null) };
    await joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      new AbortController().signal,
      { isStreamLoading: false },
    );
    expect(join).not.toHaveBeenCalled();
  });

  it("swallows abort when signal is cancelled during fetch", async () => {
    vi.mocked(fetch).mockImplementation((_url, init) => {
      const signal = init?.signal as AbortSignal | undefined;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    const ac = new AbortController();
    const join = vi.fn();
    const storage = { getItem: vi.fn().mockReturnValue(null) };
    const pending = joinActiveRunIfStaleOrMissing(
      "t1",
      storage,
      join,
      ac.signal,
    );
    ac.abort();
    await expect(pending).resolves.toBeUndefined();
    expect(join).not.toHaveBeenCalled();
  });
});

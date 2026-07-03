import { beforeEach, expect, test, vi } from "vitest";

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_BACKEND_BASE_URL: undefined as string | undefined,
    NEXT_PUBLIC_LANGGRAPH_BASE_URL: undefined as string | undefined,
  },
}));

import { env } from "@/env";
import { getBackendBaseURL } from "@/core/config";

beforeEach(() => {
  env.NEXT_PUBLIC_BACKEND_BASE_URL = undefined;
});

test("normalizes /api backend base to origin", () => {
  env.NEXT_PUBLIC_BACKEND_BASE_URL = "/api";

  expect(getBackendBaseURL()).toBe("http://localhost:2026");
});

test("normalizes full backend /api URL to origin", () => {
  env.NEXT_PUBLIC_BACKEND_BASE_URL = "http://localhost:2026/api";

  expect(getBackendBaseURL()).toBe("http://localhost:2026");
});

test("keeps backend base URL when not ending with /api", () => {
  env.NEXT_PUBLIC_BACKEND_BASE_URL = "http://localhost:18084";

  expect(getBackendBaseURL()).toBe("http://localhost:18084");
});

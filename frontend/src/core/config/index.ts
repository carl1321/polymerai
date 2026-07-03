import { env } from "@/env";

function getBaseOrigin() {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  // Fallback for SSR
  return "http://localhost:2026";
}

export function getBackendBaseURL() {
  if (env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    const url = new URL(env.NEXT_PUBLIC_BACKEND_BASE_URL, getBaseOrigin());
    // Normalize values like "/api" or ".../api" to origin so callers can safely append "/api/*".
    if (url.pathname === "/api" || url.pathname === "/api/") {
      url.pathname = "/";
    }
    return url.toString().replace(/\/+$/, "");
  } else {
    return "";
  }
}

export function getLangGraphBaseURL(isMock?: boolean) {
  console.log(
    "env.NEXT_PUBLIC_LANGGRAPH_BASE_URL",
    env.NEXT_PUBLIC_LANGGRAPH_BASE_URL,
  );
  if (env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    return new URL(
      env.NEXT_PUBLIC_LANGGRAPH_BASE_URL,
      getBaseOrigin(),
    ).toString();
  } else if (isMock) {
    if (typeof window !== "undefined") {
      return `${window.location.origin}/mock/api`;
    }
    return "http://localhost:3000/mock/api";
  } else {
    // LangGraph SDK appends paths like /threads/.../runs/stream. Gateway serves these
    // at /api/threads/... (same as REST), so apiUrl must be {origin}/api.
    if (typeof window !== "undefined") {
      return `${window.location.origin}/api`;
    }
    return "http://localhost:2026/api";
  }
}

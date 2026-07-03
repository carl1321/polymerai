"use client";

import { getBackendBaseURL } from "@/core/config";

import { clearToken, getAuthHeaders, setToken } from "./token";

const AUTH_PREFIX = "/api/auth";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    username: string;
    email: string;
    real_name?: string;
    is_superuser?: boolean;
    roles?: unknown[];
    permissions?: string[];
  };
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  real_name?: string;
  is_superuser?: boolean;
  roles?: unknown[];
  permissions?: string[];
}

async function authFetch(
  path: string,
  options: RequestInit & { requireAuth?: boolean } = {},
): Promise<Response> {
  const { requireAuth = false, ...init } = options;
  const base = getBackendBaseURL();
  const url = base ? `${base}${path}` : path;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (requireAuth) {
    Object.assign(headers, getAuthHeaders());
  }
  return fetch(url, { ...init, headers });
}

/** GET /api/auth/public-key (optional RSA for password encryption). */
export async function getPublicKey(): Promise<{ public_key?: string } | null> {
  const res = await authFetch(`${AUTH_PREFIX}/public-key`);
  if (res.status === 404 || res.status === 503) return null;
  if (!res.ok) return null;
  return res.json();
}

/** POST /api/auth/login. On success, stores token and returns user. */
export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const res = await authFetch(`${AUTH_PREFIX}/login`, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err.detail as string) || res.statusText || "Login failed");
  }
  const data = (await res.json()) as LoginResponse;
  if (data.access_token) setToken(data.access_token);
  return data;
}

/** POST /api/auth/logout (blacklist current token). Clears local token regardless. */
export async function logout(): Promise<void> {
  try {
    await authFetch(`${AUTH_PREFIX}/logout`, {
      method: "POST",
      requireAuth: true,
    });
  } finally {
    clearToken();
  }
}

/** GET /api/auth/me. Returns null if not authenticated or auth not configured. */
export async function me(): Promise<UserInfo | null> {
  const res = await authFetch(`${AUTH_PREFIX}/me`, { requireAuth: true });
  if (res.status === 401 || res.status === 404 || res.status === 503)
    return null;
  if (!res.ok) return null;
  return res.json();
}

/** POST /api/auth/refresh. Returns new token or null. */
export async function refresh(): Promise<{ access_token: string } | null> {
  const res = await authFetch(`${AUTH_PREFIX}/refresh`, {
    method: "POST",
    requireAuth: true,
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { access_token: string };
  if (data.access_token) setToken(data.access_token);
  return data;
}

export interface CasdoorAuthInfo {
  enabled: boolean;
}

/** GET /api/auth/casdoor/enabled (for login UI branching). */
export async function getCasdoorAuthInfo(): Promise<CasdoorAuthInfo> {
  const res = await authFetch(`${AUTH_PREFIX}/casdoor/enabled`);
  if (!res.ok) return { enabled: false };
  return (await res.json()) as CasdoorAuthInfo;
}

/** Returns true when Casdoor SSO is enabled. */
export async function casdoorEnabled(): Promise<boolean> {
  const info = await getCasdoorAuthInfo();
  return Boolean(info.enabled);
}

/** Full URL for starting Casdoor login (redirect). */
export function getCasdoorLoginUrl(): string {
  const base = getBackendBaseURL();
  const path = `${AUTH_PREFIX}/casdoor/login`;
  return base ? `${base}${path}` : path;
}

export interface SaTokenAuthInfo {
  enabled: boolean;
  allow_local_login: boolean;
}

/** GET /api/auth/satoken/enabled (for login UI branching). */
export async function getSaTokenAuthInfo(): Promise<SaTokenAuthInfo> {
  const res = await authFetch(`${AUTH_PREFIX}/satoken/enabled`);
  if (!res.ok) return { enabled: false, allow_local_login: true };
  return (await res.json()) as SaTokenAuthInfo;
}

/**
 * Access token storage for DeerFlow Gateway auth (localStorage).
 * Key: deer_flow_access_token
 *
 * Guest flag (sessionStorage): allow entering workspace without login when user
 * clicked "进入工作区（免登录）" on login page.
 */

const STORAGE_KEY = "deer_flow_access_token";
const GUEST_STORAGE_KEY = "deer_flow_guest";

function normalizeToken(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const value = raw.trim();
  if (!value) return null;
  if (value === "null" || value === "undefined") return null;
  if (value.startsWith("Bearer ")) {
    const stripped = value.slice("Bearer ".length).trim();
    return stripped || null;
  }
  return value;
}

function readCookieToken(name: string): string | null {
  if (typeof document === "undefined") return null;
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?:^|;\\s*)${escaped}=([^;]+)`).exec(
    document.cookie,
  );
  const token = match?.[1];
  return normalizeToken(token ? decodeURIComponent(token) : null);
}

function getTokenFromCookie(): string | null {
  return (
    readCookieToken("access_token") ??
    readCookieToken("satoken") ??
    readCookieToken("Authorization")
  );
}

function getTokenFromStorage(): string | null {
  if (typeof window === "undefined") return null;
  const local = normalizeToken(localStorage.getItem(STORAGE_KEY));
  if (local) return local;
  const continewAuth = normalizeToken(localStorage.getItem("Authorization"));
  if (continewAuth) return continewAuth;
  const continewToken = normalizeToken(localStorage.getItem("token"));
  if (continewToken) return continewToken;
  return getTokenFromCookie();
}

export function getToken(): string | null {
  return getTokenFromStorage();
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  const normalized = normalizeToken(token);
  if (!normalized) {
    clearToken();
    return;
  }
  localStorage.setItem(STORAGE_KEY, normalized);
  document.cookie = `access_token=${encodeURIComponent(normalized)}; Path=/; SameSite=Lax`;
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
  document.cookie = "access_token=; Path=/; Max-Age=0; SameSite=Lax";
}

/** Whether user entered workspace via "免登录" (guest access for this session). */
export function getGuestFlag(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(GUEST_STORAGE_KEY) === "1";
}

export function setGuestFlag(): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(GUEST_STORAGE_KEY, "1");
}

export function clearGuestFlag(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(GUEST_STORAGE_KEY);
}

/** Headers object for authenticated fetch (Bearer token). */
export function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/** Decode JWT `sub` without verification (same process as typical SPA usage). */
export function getJwtSubject(): string | null {
  const token = getToken();
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const payload = parts[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const pad = "=".repeat((4 - (base64.length % 4)) % 4);
    const json = JSON.parse(atob(base64 + pad)) as { sub?: string };
    return typeof json.sub === "string" && json.sub.trim()
      ? json.sub.trim()
      : null;
  } catch {
    return null;
  }
}

import { clearGuestFlag, clearToken, getToken } from "./token";

let installed = false;

function shouldHandle401(url: string): boolean {
  // Public share endpoints should not force redirect to /login.
  if (url.includes("/api/public/")) return false;
  // Auth endpoints (login, public key, etc.) should not be redirected globally.
  if (url.includes("/api/auth/")) return false;
  // Only handle API requests.
  return url.includes("/api/");
}

export function installGlobal401Redirect(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await originalFetch(input, init);
    if (response.status !== 401) return response;

    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (!shouldHandle401(url)) return response;
    if (!getToken()) return response;

    clearToken();
    clearGuestFlag();
    if (window.location.pathname !== "/login") {
      window.location.replace("/login");
    }
    return response;
  }) as typeof window.fetch;
}


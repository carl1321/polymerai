/**
 * Hook: on 401/Unauthorized, clear token and redirect to login.
 * Use in extension pages (agents, toolbox, etc.) so auth handling stays in extensions.
 */

import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { clearToken } from "@/core/auth";

export function useRedirectOn401(): (error: unknown) => boolean {
  const router = useRouter();
  return useCallback(
    (error: unknown): boolean => {
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.includes("Unauthorized") || msg.includes("401")) {
        clearToken();
        router.replace("/login");
        return true;
      }
      return false;
    },
    [router],
  );
}

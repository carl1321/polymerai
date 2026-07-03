"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getCasdoorAuthInfo } from "@/core/auth/api";
import { getGuestFlag, getToken } from "@/core/auth/token";

function isSafeWorkspaceReturnPath(raw: string | null): raw is string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return false;
  return raw.startsWith("/workspace");
}

/**
 * Client guard: /workspace requires a token when Casdoor is enabled, or token / guest otherwise.
 */
export function WorkspaceAuthGuard({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const token = getToken();
    if (token) {
      setAllowed(true);
      return;
    }

    const guest = getGuestFlag();

    void getCasdoorAuthInfo()
      .then((info) => {
        const casdoor = Boolean(info.enabled);
        if (casdoor || !guest) {
          const next = isSafeWorkspaceReturnPath(pathname)
            ? pathname
            : "/workspace";
          router.replace(`/login?next=${encodeURIComponent(next)}`);
          return;
        }
        setAllowed(true);
      })
      .catch(() => {
        if (!guest) {
          const next = isSafeWorkspaceReturnPath(pathname)
            ? pathname
            : "/workspace";
          router.replace(`/login?next=${encodeURIComponent(next)}`);
          return;
        }
        setAllowed(true);
      });
  }, [router, pathname]);

  if (!allowed) {
    return null;
  }

  return <>{children}</>;
}

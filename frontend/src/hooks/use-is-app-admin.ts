"use client";

import { useAuth } from "@/core/auth/AuthProvider";
import { isAppAdmin } from "@/core/auth/is-app-admin";

export function useIsAppAdmin(): boolean {
  const { user } = useAuth();
  return isAppAdmin(user ?? undefined);
}

import type { User } from "./types";

/** Aligns with backend `require_admin` (superuser or role code `admin`). */
export function isAppAdmin(
  user: User | null | undefined | Record<string, unknown>,
): boolean {
  if (!user) return false;
  const u = user as Record<string, unknown>;
  if (u.is_superuser === true) return true;
  if (u.system_role === "admin") return true;
  const roles = u.roles;
  if (Array.isArray(roles)) {
    return roles.some(
      (r) =>
        typeof r === "object" &&
        r !== null &&
        (r as { code?: string }).code === "admin",
    );
  }
  return false;
}

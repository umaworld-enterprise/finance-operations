// Where each role lands after signing in. Shared so the login redirect, the
// root page and RoleGuard cannot disagree about a user's home (5 Nov 2026 —
// the maps had been duplicated in three files).

import type { UserRole } from "@/types";

export const ROLE_HOME: Record<UserRole, string> = {
  merchandiser: "/merchandiser",
  accounts_team: "/accounts",
  finance_admin: "/finance",
  super_admin: "/admin",
  head_of_merchandiser: "/hom",
};

export function homeFor(user: { role: UserRole; onboarding_completed?: boolean }): string {
  if (user.onboarding_completed === false) return "/onboarding";
  return ROLE_HOME[user.role] ?? "/analytics";
}

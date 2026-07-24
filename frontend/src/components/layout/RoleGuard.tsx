"use client";

import { useAuth } from "@/hooks/useAuth";
import { LoadingScreen } from "@/components/ui/LoadingScreen";
import type { UserRole } from "@/types";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

const ROLE_HOME: Record<UserRole, string> = {
  merchandiser: "/merchandiser",
  accounts_team: "/accounts",
  finance_admin: "/finance",
  super_admin: "/admin",
  head_of_merchandiser: "/hom",
};

interface RoleGuardProps {
  allowedRoles: UserRole[];
  children: React.ReactNode;
}

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
    if (!loading && user && !allowedRoles.includes(user.role)) {
      router.push(ROLE_HOME[user.role] ?? "/login");
    }
  }, [user, loading, allowedRoles, router]);

  if (loading) {
    return <LoadingScreen message="Verifying access…" />;
  }

  if (!user || !allowedRoles.includes(user.role)) return null;

  return <>{children}</>;
}

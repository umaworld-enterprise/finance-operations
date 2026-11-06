"use client";

import { useAuth } from "@/hooks/useAuth";
import { ROLE_HOME } from "@/lib/role-home";
import { LoadingScreen } from "@/components/ui/LoadingScreen";
import type { UserRole } from "@/types";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

interface RoleGuardProps {
  allowedRoles: UserRole[];
  children: React.ReactNode;
}

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { user, loading, authError } = useAuth();
  const router = useRouter();
  // A backend hiccup is NOT a logout (5 Nov 2026): when /auth/me could not be
  // reached we keep the user here and say so, instead of throwing them at the
  // login screen as though their session had ended.
  const serviceDown = authError === "service_unavailable";

  useEffect(() => {
    if (loading || serviceDown) return;
    if (!user) {
      router.push("/login");
      return;
    }
    if (!allowedRoles.includes(user.role)) {
      router.push(ROLE_HOME[user.role] ?? "/login");
    }
  }, [user, loading, allowedRoles, router, serviceDown]);

  if (loading) {
    return <LoadingScreen message="Verifying access…" />;
  }

  if (serviceDown && !user) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="font-medium text-foreground">Could not reach the server</p>
        <p className="text-sm text-muted-foreground max-w-sm">
          Your session is still valid — this looks like a connection problem.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="text-sm text-primary hover:underline underline-offset-2"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!user || !allowedRoles.includes(user.role)) return null;

  return <>{children}</>;
}

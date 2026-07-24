"use client";

import { useAuth } from "@/hooks/useAuth";
import Image from "next/image";
import { useEffect } from "react";
import { LoadingScreen } from "@/components/ui/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AlertTriangle, ShieldOff, WifiOff } from "lucide-react";

const ROLE_HOME: Record<string, string> = {
  merchandiser: "/merchandiser",
  accounts_team: "/accounts",
  finance_admin: "/finance",
  super_admin: "/admin",
  head_of_merchandiser: "/hom",
};

export default function RootPage() {
  const { user, loading, authError, signOut } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!user && !authError) {
      window.location.href = "/login";
      return;
    }
    if (user) {
      window.location.href = user.onboarding_completed
        ? (ROLE_HOME[user.role] ?? "/analytics")
        : "/onboarding";
    }
  }, [user, loading, authError]);

  if (loading) {
    return <LoadingScreen message="Signing you in…" />;
  }

  if (authError === "not_registered") {
    const adminEmail = process.env.NEXT_PUBLIC_ADMIN_EMAIL ?? "admin@sunshine.com";
    const mailtoHref = `mailto:${adminEmail}?subject=${encodeURIComponent("Access Request — Finance Operations")}&body=${encodeURIComponent("Hi,\n\nI tried signing in to Finance Operations but my account hasn't been added yet.\n\nCould you please grant me access?\n\nMy Google account email: [your email here]\nMy role: [Merchandiser / Accounts Team / Finance Admin]\n\nThank you.")}`;

    return (
      <div className="flex items-center justify-center min-h-screen bg-background p-4">
        <Card className="max-w-md w-full p-8 text-center space-y-5">
          <div className="flex flex-col items-center gap-3">
            <div className="bg-white border border-border p-3 rounded-xl shadow-sm">
              <Image
                src="/logo.png"
                alt="Sunshine"
                width={36}
                height={36}
                className="h-9 w-9 object-contain"
                priority
              />
            </div>
            <div className="flex justify-center">
              <div className="bg-muted p-3 rounded-full">
                <AlertTriangle className="h-7 w-7 text-foreground" />
              </div>
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Access Not Granted Yet
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              You&apos;re signed in with Google, but your account hasn&apos;t
              been added to the system yet.
            </p>
          </div>
          <div className="rounded-lg bg-muted px-4 py-3 text-sm text-left space-y-1">
            <p className="text-muted-foreground">Contact your administrator:</p>
            <a
              href={mailtoHref}
              className="font-medium text-foreground underline underline-offset-2 break-all hover:text-primary transition-colors"
            >
              {adminEmail}
            </a>
            <p className="text-xs text-muted-foreground pt-1">
              Clicking the email above opens a pre-filled access request.
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            Once the administrator adds your email under{" "}
            <span className="font-medium text-foreground">User Management</span>,
            click <span className="font-medium text-foreground">Retry</span> —
            no further setup needed.
          </p>
          <div className="flex flex-col gap-2">
            <Button onClick={() => window.location.reload()}>Retry</Button>
            <Button variant="outline" asChild>
              <a href={mailtoHref}>Email Administrator</a>
            </Button>
            <Button variant="ghost" onClick={signOut} className="text-muted-foreground">
              Sign out &amp; try a different account
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (authError === "deactivated") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background p-4">
        <Card className="max-w-md w-full p-8 text-center space-y-4">
          <div className="flex flex-col items-center gap-3">
            <div className="bg-white border border-border p-3 rounded-xl shadow-sm">
              <Image
                src="/logo.png"
                alt="Sunshine"
                width={36}
                height={36}
                className="h-9 w-9 object-contain"
                priority
              />
            </div>
            <div className="flex justify-center">
              <div className="bg-muted p-3 rounded-full">
                <ShieldOff className="h-8 w-8 text-foreground" />
              </div>
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Account Deactivated
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Your account has been deactivated. Contact your administrator.
            </p>
          </div>
          <Button onClick={signOut} className="w-full">
            Sign out
          </Button>
        </Card>
      </div>
    );
  }

  if (authError === "service_unavailable") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background p-4">
        <Card className="max-w-md w-full p-8 text-center space-y-4">
          <div className="flex flex-col items-center gap-3">
            <div className="bg-muted p-3 rounded-full">
              <WifiOff className="h-8 w-8 text-foreground" />
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Service Temporarily Unavailable
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Could not reach the server. Please check your connection and try again.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button onClick={() => window.location.reload()}>Retry</Button>
            <Button variant="ghost" onClick={signOut} className="text-muted-foreground">
              Sign out
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  // No user + no error → redirect to login
  window.location.href = "/login";
  return <LoadingScreen message="Redirecting…" />;
}

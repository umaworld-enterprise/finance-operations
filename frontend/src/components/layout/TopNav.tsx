"use client";

import { useContext } from "react";
import { Menu } from "lucide-react";
import { SidebarContext } from "@/components/layout/sidebar-context";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { useAuth } from "@/hooks/useAuth";
import { ROLE_LABELS } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface TopNavProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function TopNav({ title, subtitle, actions }: TopNavProps) {
  const { user } = useAuth();
  const { open, setOpen } = useContext(SidebarContext);

  return (
    // Safe-area padding: in the installed PWA (viewport-fit=cover) the page
    // extends under the phone's status bar — without this the clock overlaps
    // the title. env() is 0 in regular browsers, so desktop is unchanged.
    <header className="h-[calc(4rem+env(safe-area-inset-top))] pt-[env(safe-area-inset-top)] bg-background border-b border-border flex items-center justify-between gap-3 px-4 sm:px-6 shrink-0 sticky top-0 z-20">
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="sidebar-drawer"
          className={cn(
            "lg:hidden -ml-1 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          )}
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="min-w-0">
          <h1 className="font-semibold text-foreground text-base leading-tight truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {actions}
        <NotificationBell />
        {user && (
          <span className="hidden xs:inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border border-border bg-secondary text-secondary-foreground">
            {ROLE_LABELS[user.role]}
          </span>
        )}
      </div>
    </header>
  );
}

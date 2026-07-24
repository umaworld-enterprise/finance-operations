"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, ExternalLink } from "lucide-react";
import { useMarkNotificationsRead, useNotifications } from "@/hooks/useNotifications";
import { cn, timeAgo } from "@/lib/utils";
import type { AppNotification } from "@/types";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { data } = useNotifications();
  const markRead = useMarkNotificationsRead();

  const unread = data?.unread_count ?? 0;

  // Close on outside click / Escape (no Popover primitive in the project).
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const handleRowClick = useCallback(
    (n: AppNotification) => {
      if (!n.is_read) markRead.mutate([n.id]);
      setOpen(false);
      if (n.url) router.push(n.url);
    },
    [markRead, router],
  );

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
        aria-expanded={open}
        className={cn(
          "relative p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        )}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold flex items-center justify-center">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        // On phones the bell sits near the right edge and rem-based widths
        // scale with the user's font-size setting, so an absolute right-0
        // panel can overflow the left viewport edge — anchor to the viewport
        // (fixed, below the safe-area-padded header) instead; sm+ keeps the
        // classic bell-anchored dropdown.
        <div className="fixed left-3 right-3 top-[calc(4rem+env(safe-area-inset-top)+0.5rem)] sm:absolute sm:left-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96 max-h-[70vh] overflow-y-auto rounded-xl border border-border bg-background shadow-lg z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-background">
            <p className="text-sm font-semibold text-foreground">Notifications</p>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => markRead.mutate(null)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          {!data || data.items.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted-foreground text-center">
              No notifications yet.
            </p>
          ) : (
            <ul>
              {data.items.slice(0, 8).map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => handleRowClick(n)}
                    className={cn(
                      "w-full text-left px-4 py-3 border-b border-border last:border-b-0 transition-colors hover:bg-muted/70",
                      !n.is_read && "bg-muted"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className={cn("text-sm text-foreground", !n.is_read && "font-semibold")}>
                        {n.title}
                      </p>
                      <span className="text-[11px] text-muted-foreground whitespace-nowrap shrink-0 mt-0.5">
                        {timeAgo(n.created_at)}
                      </span>
                    </div>
                    {n.body && (
                      <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>
                    )}
                    {n.attachment_url && (
                      <span
                        role="link"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          window.open(n.attachment_url!, "_blank", "noopener,noreferrer");
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.stopPropagation();
                            window.open(n.attachment_url!, "_blank", "noopener,noreferrer");
                          }
                        }}
                        className="inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full border border-border bg-secondary text-secondary-foreground text-[11px] font-medium hover:bg-muted transition-colors"
                      >
                        View TT copy
                        <ExternalLink className="h-3 w-3" />
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="sticky bottom-0 bg-background border-t border-border">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                router.push("/notifications");
              }}
              className="w-full px-4 py-3 text-sm font-medium text-primary hover:bg-muted transition-colors text-center"
            >
              View all notifications
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

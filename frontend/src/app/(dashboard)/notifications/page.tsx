"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { BellOff, CheckCheck, ExternalLink } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { Pagination } from "@/components/ui/Pagination";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useMarkNotificationsRead, useNotificationsPaginated } from "@/hooks/useNotifications";
import { cn, timeAgo } from "@/lib/utils";
import type { AppNotification } from "@/types";

const PAGE_SIZE = 20;

export default function NotificationsPage() {
  const [page, setPage] = useState(1);
  const router = useRouter();
  const { data, isLoading } = useNotificationsPaginated(page, PAGE_SIZE);
  const markRead = useMarkNotificationsRead();

  const unread = data?.unread_count ?? 0;
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleRowClick = useCallback(
    (n: AppNotification) => {
      if (!n.is_read) markRead.mutate([n.id]);
      if (n.url) router.push(n.url);
    },
    [markRead, router],
  );

  return (
    <>
      <TopNav
        title="Notifications"
        subtitle={unread > 0 ? `${unread} unread` : "You're all caught up"}
        actions={
          unread > 0 ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => markRead.mutate(null)}
              disabled={markRead.isPending}
            >
              <CheckCheck className="h-4 w-4 mr-1.5" />
              Mark all read
            </Button>
          ) : undefined
        }
      />

      <main className="flex-1 overflow-y-auto p-4 sm:p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
        <div className="max-w-3xl mx-auto">
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <p className="px-4 py-10 text-sm text-muted-foreground text-center">Loading…</p>
              ) : !data || data.items.length === 0 ? (
                <EmptyState
                  icon={BellOff}
                  title="No notifications"
                  description="Payment updates for your requests will appear here."
                />
              ) : (
                <ul>
                  {data.items.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        onClick={() => handleRowClick(n)}
                        className={cn(
                          "w-full text-left px-4 sm:px-5 py-4 border-b border-border last:border-b-0 transition-colors hover:bg-muted/70",
                          !n.is_read && "bg-muted"
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-2.5 min-w-0">
                            {!n.is_read && (
                              <span className="mt-1.5 h-2 w-2 rounded-full bg-primary shrink-0" aria-label="Unread" />
                            )}
                            <div className="min-w-0">
                              <p className={cn("text-sm text-foreground", !n.is_read && "font-semibold")}>
                                {n.title}
                              </p>
                              {n.body && (
                                <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>
                              )}
                            </div>
                          </div>
                          <span className="text-[11px] text-muted-foreground whitespace-nowrap shrink-0 mt-0.5">
                            {timeAgo(n.created_at)}
                          </span>
                        </div>
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
                            className="inline-flex items-center gap-1 mt-2 ml-4 px-2 py-0.5 rounded-full border border-border bg-secondary text-secondary-foreground text-[11px] font-medium hover:bg-muted transition-colors"
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
              <Pagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={PAGE_SIZE}
                onChange={setPage}
              />
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}

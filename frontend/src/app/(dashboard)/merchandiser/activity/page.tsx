"use client";

import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyActivity } from "@/hooks/useRequests";
import { formatDate, timeAgo } from "@/lib/utils";
import { ArrowLeft, Bell } from "lucide-react";
import Link from "next/link";
import type { RequestStatus } from "@/types";

const STATUS_BORDER: Record<RequestStatus, string> = {
  pending_payment: "border-l-amber-500",
  hold_by_merchandiser: "border-l-orange-500",
  hold_by_accounts: "border-l-orange-500",
  payment_processed: "border-l-green-500",
  cancelled_by_merchandiser: "border-l-red-500",
  cancelled_by_accounts: "border-l-red-500",
  reopened: "border-l-blue-500",
};

export default function ActivityPage() {
  const { data: activity = [], isLoading } = useMyActivity(100);

  return (
    <RoleGuard allowedRoles={["merchandiser", "super_admin"]}>
      <TopNav title="All Updates" subtitle="Full status history across your requests" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-3xl mx-auto w-full">
        <Link
          href="/merchandiser"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to my requests
        </Link>

        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-base font-semibold text-foreground">
            {isLoading ? "Loading…" : `${activity.length} update${activity.length !== 1 ? "s" : ""}`}
          </h1>
        </div>

        {isLoading ? (
          <Card>
            <CardContent className="p-5 space-y-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-32" />
                </div>
              ))}
            </CardContent>
          </Card>
        ) : activity.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <Bell className="h-8 w-8 text-muted-foreground mb-3" />
              <p className="font-semibold text-foreground">No updates yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Status changes on your requests will appear here.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {activity.map((item) => (
              <Link href={`/merchandiser/${item.request_id}`} key={item.id}>
                <div
                  className={`flex items-start gap-4 px-4 py-4 border-l-4 ${STATUS_BORDER[item.new_status]} bg-muted/20 rounded-r-lg hover:bg-muted/40 transition-colors`}
                >
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-semibold bg-muted px-1.5 py-0.5 rounded">
                        {item.request_number}
                      </span>
                      <span className="text-sm font-medium text-foreground">{item.supplier_name}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {item.old_status && (
                        <>
                          <StatusBadge status={item.old_status} showFull />
                          <span className="text-xs text-muted-foreground">→</span>
                        </>
                      )}
                      <StatusBadge status={item.new_status} showFull />
                    </div>
                    {item.remarks && (
                      <p className="text-xs text-muted-foreground italic">
                        &ldquo;{item.remarks}&rdquo;
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0 space-y-0.5">
                    <p className="text-xs text-muted-foreground whitespace-nowrap">{timeAgo(item.changed_at)}</p>
                    <p className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(item.changed_at)}</p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </RoleGuard>
  );
}

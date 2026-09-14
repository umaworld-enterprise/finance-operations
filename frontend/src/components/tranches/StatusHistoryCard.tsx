"use client";

// Shared Status History card (19 Aug 2026): request status transitions
// merged with tranche rejections. A rejected tranche deliberately never
// changes the REQUEST status (the merchandiser adds replacement tranches),
// but the history must still show the rejection — before this, the timeline
// looked stuck on "Pending Payment" after Accounts rejected a tranche.
// Used by the merchandiser, accounts and HoM request detail pages.

import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/utils";
import type { PaymentTranche, StatusHistory } from "@/types";

type Entry =
  | { kind: "status"; key: string; at: string; h: StatusHistory }
  | { kind: "tranche_rejected"; key: string; at: string; label: string; reason: string | null };

export function StatusHistoryCard({
  history,
  tranches,
}: {
  history: StatusHistory[] | null | undefined;
  tranches: PaymentTranche[] | null | undefined;
}) {
  const rejections = (tranches ?? []).filter((t) => t.status === "rejected");
  const entries: Entry[] = [
    ...(history ?? []).map((h) => ({
      kind: "status" as const,
      key: `s-${h.id}`,
      at: h.changed_at,
      h,
    })),
    ...rejections.map((t) => ({
      kind: "tranche_rejected" as const,
      key: `t-${t.id}`,
      at: t.rejected_at ?? "",
      label: t.label,
      reason: t.rejection_reason,
    })),
  ].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));

  if (entries.length === 0) return null;

  return (
    <Card>
      <CardContent className="p-5 md:p-6">
        <h2 className="text-sm font-semibold text-foreground mb-4">Status History</h2>
        <ol className="space-y-3">
          {entries.map((e) => (
            <li key={e.key} className="flex flex-col sm:flex-row gap-1 sm:gap-3 text-sm">
              <span className="text-muted-foreground shrink-0 sm:w-32 text-xs pt-0.5">
                {e.at ? formatDate(e.at) : "—"}
              </span>
              <span className="flex-1">
                {e.kind === "status" ? (
                  <>
                    {e.h.old_status ? (
                      <>
                        <StatusBadge status={e.h.old_status} />
                        <span className="mx-1.5 text-muted-foreground">→</span>
                      </>
                    ) : null}
                    <StatusBadge status={e.h.new_status} showFull />
                    {e.h.remarks && (
                      <p className="text-xs text-muted-foreground mt-0.5">{e.h.remarks}</p>
                    )}
                  </>
                ) : (
                  <>
                    <span className="inline-flex items-center text-xs font-medium border px-2 py-0.5 rounded-full text-red-700 bg-red-50 border-red-200">
                      Rejected — {e.label}
                    </span>
                    {e.reason && (
                      <p className="text-xs text-muted-foreground mt-0.5">{e.reason}</p>
                    )}
                  </>
                )}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

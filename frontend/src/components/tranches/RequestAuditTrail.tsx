"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRequestAuditTrail } from "@/hooks/useRequests";
import { formatDate } from "@/lib/utils";

const ENTITY_LABELS: Record<string, string> = {
  deposit_requests: "Request",
  payment_details: "Payment",
  payment_tranches: "Tranche",
  invoice_adjustments: "Adjustment",
};

/** Collapsible audit history for a request — covers the request itself, its
 * tranches and any invoice adjustments touching them. */
export function RequestAuditTrail({ requestId }: { requestId: string }) {
  const [open, setOpen] = useState(false);
  const { data: entries = [], isLoading } = useRequestAuditTrail(requestId);

  return (
    <Card>
      <CardContent className="p-5 md:p-6">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <div>
            <h2 className="text-sm font-semibold text-foreground">Audit History</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Who changed what and when — including tranche payments and invoice adjustments.
            </p>
          </div>
          {open ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
          )}
        </button>

        {open && (
          <div className="mt-4">
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : entries.length === 0 ? (
              <p className="text-sm text-muted-foreground">No audit entries yet.</p>
            ) : (
              <ol className="space-y-3">
                {entries.map((e) => (
                  <li key={e.id} className="flex flex-col sm:flex-row gap-1 sm:gap-3 text-sm">
                    <span className="text-muted-foreground shrink-0 sm:w-32 text-xs pt-0.5">
                      {formatDate(e.changed_at)}
                    </span>
                    <span className="flex-1">
                      <span className="text-xs font-medium text-muted-foreground border border-border rounded-full px-2 py-0.5 mr-2">
                        {ENTITY_LABELS[e.entity_name] ?? e.entity_name}
                      </span>
                      <span className="font-medium text-foreground">{e.action}</span>
                      {e.field_name && <span className="text-muted-foreground"> · {e.field_name}</span>}
                      {(e.old_value || e.new_value) && (
                        <p className="text-xs text-muted-foreground mt-0.5 break-words">
                          {e.old_value != null && <>{e.old_value} → </>}
                          {e.new_value}
                        </p>
                      )}
                      {e.changed_by_name && (
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          by {e.changed_by_name}
                        </p>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

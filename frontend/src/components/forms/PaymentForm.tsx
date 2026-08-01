"use client";

// Ship Date panel (Aug 2026 follow-up). The request-level Payment Details
// form (payment date / bank / reference / status / remarks) was REMOVED —
// those details are captured per tranche in the Advance Payment Tranches
// panel, and the backend derives request-level payment_date/payment_status
// from the tranches when the final one is paid (analytics + report exports
// keep working). What remains here:
//   - Ship Date: the designed post-lock action that stops Cost of Fund
//     accrual, drives shipment analytics, and excludes the request from
//     Adjust Invoices.
//   - The legacy request-level TT copy link (pre-tranche records), view-only.

import { toast } from "sonner";
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { useSaveShipDate } from "@/hooks/useRequests";
import { Button } from "@/components/ui/button";
import type { PaymentDetails } from "@/types";

interface Props {
  requestId: string;
  existing?: PaymentDetails | null;
}

export function PaymentForm({ requestId, existing }: Props) {
  const saveShipDate = useSaveShipDate();

  const [shipDate, setShipDate] = useState("");
  useEffect(() => {
    setShipDate(existing?.ship_date ?? "");
  }, [existing?.ship_date]);

  const onSaveShipDate = async () => {
    if (!shipDate) return;
    try {
      await saveShipDate.mutateAsync({ requestId, shipDate });
      toast.success("Ship date saved — Cost of Fund has been frozen at this date.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save ship date.");
    }
  };

  return (
    <div className="space-y-5">
      {/* Ship Date — stays interactive even when locked: payment is processed
          (which locks the record) long before the goods actually ship. Recording
          the real ship date here is what stops Cost of Fund accrual. */}
      <div className="space-y-3">
        <div>
          <p className="text-sm font-medium text-foreground">Ship Date</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            The actual date the goods were shipped. Recording it stops Cost of Fund
            accrual — it can be entered or corrected even after the record is locked.
            Payment details are recorded per tranche in the panel above.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <input
            type="date"
            value={shipDate}
            onChange={(e) => setShipDate(e.target.value)}
            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button
            type="button"
            onClick={onSaveShipDate}
            disabled={!shipDate || saveShipDate.isPending}
            className="w-full sm:w-auto"
          >
            {saveShipDate.isPending ? "Saving…" : existing?.ship_date ? "Update Ship Date" : "Save Ship Date"}
          </Button>
        </div>
      </div>

      {/* Legacy request-level TT copy (pre-tranche records) — view only. */}
      {existing?.tt_copy_url && (
        <div className="pt-4 border-t border-border space-y-2">
          <p className="text-sm font-medium text-foreground">TT Copy (legacy)</p>
          <p className="text-xs text-muted-foreground">
            Request-level TT copy from before tranche-level payments.
          </p>
          <a
            href={existing.tt_copy_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-secondary text-secondary-foreground text-xs font-medium hover:bg-muted transition-colors"
          >
            View TT copy{existing.tt_copy_filename ? ` — ${existing.tt_copy_filename}` : ""}
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { useRequestAdjustments } from "@/hooks/useRequests";
import { formatCurrency, formatDate } from "@/lib/utils";

/** Invoice adjustments touching this request's tranches — reallocations are
 * traceable from both the source request and the destination invoice. Hidden
 * entirely when there are none. */
export function RequestAdjustments({
  requestId,
  currency,
  linkBase,
}: {
  requestId: string;
  currency: string | null;
  /** Route prefix for cross-links to the other request, e.g. "/accounts". */
  linkBase: string;
}) {
  const { data: adjustments = [] } = useRequestAdjustments(requestId);
  if (adjustments.length === 0) return null;

  return (
    <Card>
      <CardContent className="p-5 md:p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1">Invoice Adjustments</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Value reallocated between this request and other invoices of the same supplier.
          The original paid tranches remain unchanged historical records.
        </p>
        <ol className="space-y-3">
          {adjustments.map((a) => {
            const isOutgoing = a.source_request_id === requestId;
            const otherRequestId = isOutgoing ? a.destination_request_id : a.source_request_id;
            const otherNumber = isOutgoing ? a.destination_request_number : a.source_request_number;
            return (
              <li key={a.id} className="text-sm border border-border rounded-lg p-3">
                <p className="font-medium text-foreground">
                  {formatCurrency(a.amount, currency ?? undefined)}{" "}
                  {isOutgoing ? (
                    <>reallocated from {a.source_tranche_label} to</>
                  ) : (
                    <>received on {a.destination_tranche_label} from</>
                  )}{" "}
                  {otherRequestId ? (
                    <Link
                      href={`${linkBase}/${otherRequestId}`}
                      className="text-primary underline underline-offset-2 hover:opacity-80"
                    >
                      {otherNumber}
                    </Link>
                  ) : (
                    otherNumber
                  )}
                  {isOutgoing ? ` / ${a.destination_tranche_label}` : ` / ${a.source_tranche_label}`}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {formatDate(a.created_at)}
                  {a.performed_by_name ? ` · by ${a.performed_by_name}` : ""}
                  {a.reason ? ` · ${a.reason}` : ""}
                </p>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

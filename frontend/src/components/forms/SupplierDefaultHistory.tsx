"use client";

// Supplier default history on request detail pages (Aug 2026 follow-up):
// when the request's supplier has ever been flagged, approvers see the full
// track record — active flag first — right below the Analytics Snapshot,
// so decisions are made with the history in view. Renders nothing for
// suppliers with a clean record. Used app-wide: HoM, Accounts and
// Merchandiser request detail views.

import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useSupplierDefaultHistory } from "@/hooks/useMasters";
import { formatCurrency, formatDate } from "@/lib/utils";

interface Props {
  supplierId: string | null | undefined;
  supplierName: string;
}

export function SupplierDefaultHistory({ supplierId, supplierName }: Props) {
  const { data: history = [] } = useSupplierDefaultHistory(supplierId ?? null);

  if (history.length === 0) return null;

  const active = history.find((f) => f.is_active);

  return (
    <Card className={active ? "border-amber-300" : undefined}>
      <CardContent className="p-5 md:p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
          <AlertTriangle className={`h-4 w-4 ${active ? "text-amber-600" : "text-muted-foreground"}`} />
          Supplier Default History — {supplierName}
        </h2>
        <p className="text-xs text-muted-foreground mb-3">
          {active
            ? "This supplier is CURRENTLY on the defaulted list. Review the record below before approving or paying."
            : "This supplier has past default records (all resolved). Shown for context."}
        </p>

        {active && (
          <div className="rounded-lg bg-amber-50 border border-amber-300 text-amber-800 p-3 text-sm mb-3">
            <span className="font-semibold">Active flag:</span>{" "}
            {active.default_reason} — outstanding{" "}
            {formatCurrency(Number(active.outstanding_amount), active.currency)}
            {" "}(flagged {formatDate(active.flagged_date)})
          </div>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Flagged</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead className="text-right">Outstanding</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="text-xs whitespace-nowrap">{formatDate(f.flagged_date)}</TableCell>
                  <TableCell className="text-sm">{f.default_reason}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {formatCurrency(Number(f.outstanding_amount), f.currency)}
                  </TableCell>
                  <TableCell>
                    {f.is_active ? (
                      <span className="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full whitespace-nowrap">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full whitespace-nowrap">
                        Resolved{f.resolved_date ? ` ${formatDate(f.resolved_date)}` : ""}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

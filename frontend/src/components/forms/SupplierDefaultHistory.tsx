"use client";

// Supplier default history on request detail pages (Aug 2026 follow-up):
// when the request's supplier has ever been flagged, approvers see the full
// track record — active flag first — right below the Analytics Snapshot,
// so decisions are made with the history in view.
//
// UAT change note Aug 2026 (item 2): the panel now also shows the
// supplier's WHOLE live exposure — every open request (not cancelled or
// rejected, goods not yet shipped) — split into "Graced ETD passed" and
// "Graced ETD not yet passed", with per-currency totals. Rendered whenever
// the supplier has flags OR live exposure. Used app-wide: HoM, Accounts
// and Merchandiser request detail views.

import { AlertTriangle, CalendarClock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useSupplierDefaultHistory, useSupplierExposure } from "@/hooks/useMasters";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { SupplierExposureRow } from "@/types";

interface Props {
  supplierId: string | null | undefined;
  supplierName: string;
}

function ExposureRows({ rows, overdue }: { rows: SupplierExposureRow[]; overdue: boolean }) {
  return (
    <TableBody>
      {rows.map((r) => (
        <TableRow key={r.request_id}>
          <TableCell className="font-mono text-xs whitespace-nowrap">{r.request_number}</TableCell>
          <TableCell className="text-right tabular-nums text-sm">
            {formatCurrency(Number(r.deposit_amount), r.currency)}
          </TableCell>
          <TableCell><StatusBadge status={r.current_status} /></TableCell>
          <TableCell className="text-xs whitespace-nowrap">{formatDate(r.grace_etd)}</TableCell>
          <TableCell className="text-xs">
            {overdue && r.etd_grace_overdue_days != null ? (
              <span className="text-red-700 font-medium">{r.etd_grace_overdue_days}d overdue</span>
            ) : (
              "—"
            )}
          </TableCell>
        </TableRow>
      ))}
    </TableBody>
  );
}

function ExposureSection({
  title,
  hint,
  rows,
  overdue,
}: {
  title: string;
  hint: string;
  rows: SupplierExposureRow[];
  overdue: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold text-foreground">{title}</p>
      <p className="text-xs text-muted-foreground mb-2">{hint}</p>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Grace ETD</TableHead>
              <TableHead>Overdue</TableHead>
            </TableRow>
          </TableHeader>
          <ExposureRows rows={rows} overdue={overdue} />
        </Table>
      </div>
    </div>
  );
}

export function SupplierDefaultHistory({ supplierId, supplierName }: Props) {
  const { data: history = [] } = useSupplierDefaultHistory(supplierId ?? null);
  const { data: exposure } = useSupplierExposure(supplierId ?? null);

  const exposureRows =
    (exposure?.graced_etd_passed.length ?? 0) + (exposure?.graced_etd_pending.length ?? 0);
  if (history.length === 0 && exposureRows === 0) return null;

  const active = history.find((f) => f.is_active);
  const hasGracedPassed = (exposure?.graced_etd_passed.length ?? 0) > 0;

  return (
    <Card className={active || hasGracedPassed ? "border-amber-300" : undefined}>
      <CardContent className="p-5 md:p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
          <AlertTriangle
            className={`h-4 w-4 ${active || hasGracedPassed ? "text-amber-600" : "text-muted-foreground"}`}
          />
          Supplier Default History — {supplierName}
        </h2>
        <p className="text-xs text-muted-foreground mb-3">
          {active
            ? "This supplier is CURRENTLY on the defaulted list. Review the record below before approving or paying."
            : history.length > 0
              ? "This supplier has past default records (all resolved). Shown for context."
              : "No default flags — live exposure shown for context."}
        </p>

        {active && (
          <div className="rounded-lg bg-amber-50 border border-amber-300 text-amber-800 p-3 text-sm mb-3">
            <span className="font-semibold">Active flag:</span>{" "}
            {active.default_reason} — outstanding{" "}
            {formatCurrency(Number(active.outstanding_amount), active.currency)}
            {" "}(flagged {formatDate(active.flagged_date)})
          </div>
        )}

        {history.length > 0 && (
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
        )}

        {/* Whole live exposure (UAT Aug 2026, item 2) */}
        {exposure && exposureRows > 0 && (
          <div className="mt-5 pt-4 border-t border-border">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-muted-foreground" />
              Live Exposure
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Every open file with this supplier (goods not yet shipped).{" "}
              Total:{" "}
              {Object.entries(exposure.totals_by_currency)
                .map(([cur, amt]) => formatCurrency(Number(amt), cur === "—" ? null : cur))
                .join(" + ")}
            </p>
            <ExposureSection
              title="Graced ETD passed"
              hint="The grace period has expired and goods have not shipped — defaulting behaviour."
              rows={exposure.graced_etd_passed}
              overdue
            />
            <ExposureSection
              title="Graced ETD not yet passed"
              hint="Open commitments still inside the grace window."
              rows={exposure.graced_etd_pending}
              overdue={false}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

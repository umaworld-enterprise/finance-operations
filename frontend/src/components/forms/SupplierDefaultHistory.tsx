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
  /** The request currently being viewed — its amount drives the
   * "Potential Exposure after approving this request" KPI (10 Aug 2026):
   * Existing Exposure excludes this file; Potential = Existing + this
   * file's deposit. */
  currentRequest?: {
    id: string;
    deposit_amount: number;
    currency: string | null;
  };
}

function ExposureRows({ rows, overdue }: { rows: SupplierExposureRow[]; overdue: boolean }) {
  return (
    <TableBody>
      {rows.map((r) => (
        <TableRow key={r.request_id}>
          <TableCell className="font-mono text-xs whitespace-nowrap">{r.request_number}</TableCell>
          {/* Overdue files carry the Sunshine Invoice No. so the risk rows
              can be chased by invoice (19 Aug 2026). */}
          {overdue && (
            <TableCell className="font-mono text-xs whitespace-nowrap">
              {r.sunshine_invoice_number ?? "—"}
            </TableCell>
          )}
          <TableCell className="text-right tabular-nums text-sm">
            {formatCurrency(Number(r.deposit_amount), r.currency)}
          </TableCell>
          <TableCell><StatusBadge status={r.current_status} /></TableCell>
          <TableCell className="text-xs whitespace-nowrap">{formatDate(r.grace_etd)}</TableCell>
          <TableCell className="text-xs">
            {overdue && r.etd_grace_overdue_days != null && r.etd_grace_overdue_days > 0 ? (
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
              {overdue && <TableHead>Sunshine Invoice #</TableHead>}
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

export function SupplierDefaultHistory({ supplierId, supplierName, currentRequest }: Props) {
  const { data: history = [] } = useSupplierDefaultHistory(supplierId ?? null);
  const { data: exposure } = useSupplierExposure(supplierId ?? null);

  const exposureRows =
    (exposure?.graced_etd_passed.length ?? 0) + (exposure?.graced_etd_pending.length ?? 0);
  if (history.length === 0 && exposureRows === 0) return null;

  const active = history.find((f) => f.is_active);
  const hasGracedPassed = (exposure?.graced_etd_passed.length ?? 0) > 0;

  // Exposure KPIs (10 Aug 2026; recalibrated 11 Aug), per currency.
  //   Existing Exposure = Overdue Payments + Payments in Process:
  //     - Overdue Payments: processed payments past the graced ETD
  //       (goods not shipped);
  //     - Payments in Process: processed payments still inside the grace
  //       window, PLUS payment requests already approved by HoM and
  //       sitting in the payment queue (pending_payment) even if Accounts
  //       have not processed them yet.
  //   Requests still awaiting HoM approval, on hold or reopened are NOT
  //   exposure (they stay visible in the breakdown tables below).
  //   Excludes the request being viewed.
  //   Potential = Existing + this request's deposit (i.e. once approved).
  //   A currency column appears only when it has existing exposure or this
  //   request would add it.
  const EXPOSURE_STATUSES = new Set(["payment_processed", "pending_payment"]);
  const allExposure = [
    ...(exposure?.graced_etd_passed ?? []),
    ...(exposure?.graced_etd_pending ?? []),
  ];
  const existingByCurrency: Record<string, number> = {};
  for (const row of allExposure) {
    if (currentRequest && row.request_id === currentRequest.id) continue;
    if (!EXPOSURE_STATUSES.has(row.current_status)) continue;
    const key = row.currency ?? "—";
    existingByCurrency[key] = (existingByCurrency[key] ?? 0) + Number(row.deposit_amount);
  }
  const potentialByCurrency: Record<string, number> = { ...existingByCurrency };
  if (currentRequest) {
    const key = currentRequest.currency ?? "—";
    potentialByCurrency[key] =
      (potentialByCurrency[key] ?? 0) + Number(currentRequest.deposit_amount);
  }
  const exposureCurrencies = Array.from(
    new Set([...Object.keys(existingByCurrency), ...Object.keys(potentialByCurrency)]),
  ).sort();

  return (
    <Card className={active || hasGracedPassed ? "border-amber-300" : undefined}>
      <CardContent className="p-5 md:p-6">
        <h2 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
          <AlertTriangle
            className={`h-4 w-4 ${active || hasGracedPassed ? "text-amber-600" : "text-muted-foreground"}`}
          />
          Supplier Default History — {supplierName}
        </h2>
        {/* 10 Aug 2026: red-flag wording; the amber "Active flag" box was removed. */}
        {active ? (
          <p className="text-xs font-medium text-red-700 mb-3">
            Red flag: this supplier has been listed under &ldquo;Default Advance
            Payment List&rdquo;. Kindly review its history before making any decision.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">
            {history.length > 0
              ? "This supplier has past default records (all resolved). Shown for context."
              : "No default flags — live exposure shown for context."}
          </p>
        )}

        {/* 10 Aug refinement: the flag-history table (Flagged / Reason /
            Outstanding / Status) was removed from this card — the red-flag
            line above carries the warning; the full flag records live on
            the Supplier Risk page for finance admins. */}

        {/* Whole live exposure (UAT Aug 2026, item 2; KPI table 10 Aug) */}
        {exposure && exposureRows > 0 && (
          <div className="mt-5 pt-4 border-t border-border">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-muted-foreground" />
              Live Exposure
            </h3>
            {exposureCurrencies.length > 0 && (
              <div className="overflow-x-auto mt-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="min-w-56" />
                      {exposureCurrencies.map((cur) => (
                        <TableHead key={cur} className="text-right">{cur}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="text-xs">
                        <span className="font-medium text-foreground">Existing Exposure</span>{" "}
                        <span className="text-muted-foreground">(Overdue payments + Payments in process)</span>
                      </TableCell>
                      {exposureCurrencies.map((cur) => (
                        <TableCell key={cur} className="text-right tabular-nums text-sm">
                          {formatCurrency(existingByCurrency[cur] ?? 0, cur === "—" ? null : cur)}
                        </TableCell>
                      ))}
                    </TableRow>
                    {currentRequest && (
                      <TableRow>
                        <TableCell className="text-xs">
                          <span className="font-medium text-foreground">Potential Exposure</span>{" "}
                          <span className="text-muted-foreground">after approving this request</span>
                        </TableCell>
                        {exposureCurrencies.map((cur) => (
                          <TableCell key={cur} className="text-right tabular-nums text-sm font-semibold">
                            {formatCurrency(potentialByCurrency[cur] ?? 0, cur === "—" ? null : cur)}
                          </TableCell>
                        ))}
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
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

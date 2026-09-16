"use client";

import Link from "next/link";
import { amountPayable, formatCurrency, formatDate, hasHighPriorityUnpaid, requestDisplayNumber } from "@/lib/utils";
import { latestPaymentDate } from "@/lib/exportExcel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { DepositRequest } from "@/types";
import { ClipboardList, ArrowUpRight } from "lucide-react";
import { SortableHead, sortByColumn, useColumnSortState, type ColumnAccessors } from "@/components/ui/SortableHead";

// Column-header sorting (16 Sep 2026, executive request).
const ACCESSORS: ColumnAccessors<DepositRequest> = {
  request:      (r) => requestDisplayNumber(r),
  invoice:      (r) => r.sunshine_invoice_number,
  supplier:     (r) => r.supplier?.name,
  customer:     (r) => r.customer?.name,
  vertical:     (r) => r.vertical?.name,
  merchandiser: (r) => r.creator?.full_name,
  payable:      (r) => amountPayable(r),
  deposit:      (r) => Number(r.deposit_amount),
  status:       (r) => r.current_status,
  payment_date: (r) => latestPaymentDate(r),
  submitted:    (r) => r.created_at,
};

interface RequestsTableProps {
  requests: DepositRequest[];
  basePath?: string;
  emptyMessage?: string;
  /** Show WHO raised each request — used since all requests became visible
   * to every merchandiser (11 Sep 2026). */
  showMerchandiser?: boolean;
}

export function RequestsTable({
  requests,
  basePath = "/merchandiser",
  emptyMessage = "Requests you submit will appear here.",
  showMerchandiser = false,
}: RequestsTableProps) {
  // Column-header sorting (16 Sep 2026) — client-side over the loaded rows.
  const colSort = useColumnSortState();
  requests = sortByColumn(requests, ACCESSORS, colSort.sort);
  if (requests.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="No requests found"
        description={emptyMessage}
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <SortableHead label="Request #" sortKey="request" state={colSort} />
            <SortableHead label="Invoice #" sortKey="invoice" state={colSort} className="hidden sm:table-cell" />
            <SortableHead label="Supplier" sortKey="supplier" state={colSort} />
            <SortableHead label="Customer" sortKey="customer" state={colSort} />
            <SortableHead label="Vertical" sortKey="vertical" state={colSort} className="hidden md:table-cell" />
            {showMerchandiser && (
              <SortableHead label="Merchandiser" sortKey="merchandiser" state={colSort} className="hidden md:table-cell" />
            )}
            <SortableHead label="Amount Payable" sortKey="payable" state={colSort} align="right" className="hidden sm:table-cell text-right" />
            <SortableHead label="Deposit" sortKey="deposit" state={colSort} align="right" className="text-right" />
            <SortableHead label="Status" sortKey="status" state={colSort} />
            <SortableHead label="Payment Date" sortKey="payment_date" state={colSort} className="hidden md:table-cell" />
            <SortableHead label="Submitted" sortKey="submitted" state={colSort} className="hidden lg:table-cell" />
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.map((req) => (
            <TableRow key={req.id}>
              <TableCell>
                <div className="flex items-center gap-1.5">
                  <Link
                    href={`${basePath}/${req.id}`}
                    className="font-mono text-xs text-foreground font-semibold hover:underline underline-offset-2"
                  >
                    {requestDisplayNumber(req)}
                  </Link>
                  {/* Priority badge (5 Sep 2026) — display only, no re-ordering. */}
                  {hasHighPriorityUnpaid(req) && (
                    <span className="inline-flex items-center text-[10px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded-full whitespace-nowrap">
                      High
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell className="hidden sm:table-cell font-mono text-xs text-muted-foreground">
                {req.sunshine_invoice_number || "—"}
              </TableCell>
              <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
              <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
              <TableCell className="hidden md:table-cell text-muted-foreground text-xs">
                {req.vertical?.name ?? "—"}
              </TableCell>
              {showMerchandiser && (
                <TableCell className="hidden md:table-cell text-muted-foreground text-xs">
                  {req.creator?.full_name ?? "—"}
                </TableCell>
              )}
              <TableCell className="hidden sm:table-cell text-right font-semibold text-foreground">
                {formatCurrency(amountPayable(req), req.currency)}
              </TableCell>
              <TableCell className="text-right font-semibold text-foreground">
                {formatCurrency(req.deposit_amount, req.currency)}
              </TableCell>
              <TableCell>
                <StatusBadge status={req.current_status} />
              </TableCell>
              {/* Payment date beside every paid amount (2 Sep 2026). */}
              <TableCell className="hidden md:table-cell text-muted-foreground text-xs whitespace-nowrap">
                {latestPaymentDate(req) ? formatDate(latestPaymentDate(req)) : "—"}
              </TableCell>
              <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">
                {formatDate(req.created_at)}
              </TableCell>
              <TableCell>
                <Button size="sm" variant="ghost" asChild>
                  <Link href={`${basePath}/${req.id}`} aria-label={`View request ${requestDisplayNumber(req)}`}>
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

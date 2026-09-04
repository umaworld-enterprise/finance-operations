"use client";

// Bank Ledger tab (4 Sep 2026, executive request): the pending payments
// rendered on screen in the executives' Excel ledger layout — the same
// entries the "Export in Bank Ledger" option downloads, no download needed.
// Voucher No., Rate, Credit and BALANCE are maintained manually in Excel
// (no such data in the system) and render empty here, like the export.

import { useState } from "react";
import { BookOpen } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BankLedgerEntry } from "@/lib/exportExcel";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 50;

function num(value: number | null): string {
  return value == null
    ? ""
    : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function BankLedgerTable({
  entries,
  loading,
}: {
  entries: BankLedgerEntry[];
  loading: boolean;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rows = entries.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Total value (4 Sep 2026, executive request) — per currency, over ALL
  // entries (not just the visible page): the Currency amounts and the Debit
  // (paid) portion. Currencies cannot be summed together.
  const totals = new Map<string, { amount: number; debit: number }>();
  for (const e of entries) {
    const key = e.curr || "—";
    const row = totals.get(key) ?? { amount: 0, debit: 0 };
    row.amount += e.amount;
    row.debit += e.debit ?? 0;
    totals.set(key, row);
  }
  const totalRows = [...totals.entries()].sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-foreground text-sm">Pending Payments — Bank Ledger</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          One row per tranche, oldest first — paid tranches carry their payment date and Debit;
          unpaid tranches show the request date. Voucher No., Rate, Credit and BALANCE are
          maintained in Excel and stay empty here.
        </p>
      </div>
      {!loading && entries.length === 0 ? (
        <div className="p-6">
          <EmptyState
            icon={BookOpen}
            title="No ledger entries"
            description="There are no pending-payment tranches to show."
          />
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                {/* Dark header band, like the executives' Excel ledger. */}
                <TableRow className="bg-foreground hover:bg-foreground">
                  <TableHead className="text-background whitespace-nowrap">Date</TableHead>
                  <TableHead className="text-background">Supplier</TableHead>
                  <TableHead className="text-background whitespace-nowrap">Voucher No.</TableHead>
                  <TableHead className="text-background whitespace-nowrap">File Nos.</TableHead>
                  <TableHead className="text-background">Customer</TableHead>
                  <TableHead className="text-background">Curr</TableHead>
                  <TableHead className="text-background text-right whitespace-nowrap">Currency</TableHead>
                  <TableHead className="text-background text-right">Rate</TableHead>
                  <TableHead className="text-background text-right">Debit</TableHead>
                  <TableHead className="text-background text-right">Credit</TableHead>
                  <TableHead className="text-background text-right">BALANCE</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableSkeleton rows={6} cols={11} />
                ) : (
                  rows.map((e, i) => (
                    <TableRow key={i}>
                      <TableCell className="whitespace-nowrap text-sm">
                        {e.date ? formatDate(e.date) : ""}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{e.supplier}</TableCell>
                      <TableCell />
                      <TableCell className="whitespace-nowrap text-sm">{e.file_nos}</TableCell>
                      <TableCell className="text-sm">{e.customer}</TableCell>
                      <TableCell className="text-sm">{e.curr}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{num(e.amount)}</TableCell>
                      <TableCell />
                      <TableCell className="text-right text-sm tabular-nums">{num(e.debit)}</TableCell>
                      <TableCell />
                      <TableCell />
                    </TableRow>
                  ))
                )}
                {/* Total value per currency — over the whole ledger, not
                    just this page. */}
                {!loading &&
                  totalRows.map(([curr, sums]) => (
                    <TableRow key={`total-${curr}`} className="bg-muted/60 hover:bg-muted/60 font-semibold">
                      <TableCell className="text-sm" colSpan={5}>
                        Total value{totalRows.length > 1 || curr !== "—" ? ` (${curr})` : ""}
                      </TableCell>
                      <TableCell className="text-sm">{curr}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{num(sums.amount)}</TableCell>
                      <TableCell />
                      <TableCell className="text-right text-sm tabular-nums">
                        {sums.debit > 0 ? num(sums.debit) : ""}
                      </TableCell>
                      <TableCell />
                      <TableCell />
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
          <div className="px-4 pb-4">
            <Pagination
              page={safePage}
              totalPages={totalPages}
              total={entries.length}
              pageSize={PAGE_SIZE}
              onChange={setPage}
            />
          </div>
        </>
      )}
    </Card>
  );
}

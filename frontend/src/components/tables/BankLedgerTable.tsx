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
import { formatDateSheet } from "@/lib/utils";
import { SortableHead, sortByColumn, useColumnSortState, type ColumnAccessors } from "@/components/ui/SortableHead";

const PAGE_SIZE = 50;

// Column-header sorting (16 Sep 2026, executive request).
const ACCESSORS: ColumnAccessors<BankLedgerEntry> = {
  date:     (e) => e.date,
  supplier: (e) => e.supplier,
  proforma: (e) => e.supplier_invoice,
  file_nos: (e) => e.file_nos,
  customer: (e) => e.customer,
  curr:     (e) => e.curr,
  debit:    (e) => e.amount,
};

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
  // Column-header sorting (16 Sep 2026) — applied to the WHOLE ledger before
  // pagination, so asc/desc runs across every page.
  const colSort = useColumnSortState();
  const sortedEntries = sortByColumn(entries, ACCESSORS, colSort.sort);
  const totalPages = Math.max(1, Math.ceil(sortedEntries.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rows = sortedEntries.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Total value (4 Sep 2026, executive request) — per currency, over ALL
  // entries (not just the visible page). Currencies cannot be summed together.
  const totals = new Map<string, number>();
  for (const e of entries) {
    const key = e.curr || "—";
    totals.set(key, (totals.get(key) ?? 0) + e.amount);
  }
  const totalRows = [...totals.entries()].sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-foreground text-sm">Pending Payments — Bank Ledger</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          One row per UNPAID tranche (amounts still to be paid), oldest first — the amount sits
          in Debit, dated by the request date. EURO/CNY, Rate, Credit and BALANCE are maintained
          in Excel and stay empty here.
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
                  {/* Asc/desc on every data-bearing header (16 Sep 2026). */}
                  <SortableHead label="Date" sortKey="date" state={colSort} className="text-background whitespace-nowrap" />
                  <SortableHead label="Supplier" sortKey="supplier" state={colSort} className="text-background" />
                  <SortableHead label="Supplier Proforma Invoice #" sortKey="proforma" state={colSort} className="text-background whitespace-nowrap" />
                  <SortableHead label="File Nos." sortKey="file_nos" state={colSort} className="text-background whitespace-nowrap" />
                  <SortableHead label="Customer" sortKey="customer" state={colSort} className="text-background" />
                  <SortableHead label="Curr" sortKey="curr" state={colSort} className="text-background" />
                  {/* Kept empty for now (client decision, 4 Sep 2026). */}
                  <TableHead className="text-background text-right whitespace-nowrap">EURO/CNY</TableHead>
                  <TableHead className="text-background text-right">Rate</TableHead>
                  <SortableHead label="Debit" sortKey="debit" state={colSort} align="right" className="text-background text-right" />
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
                      {/* DD-Mon-YY (16 Sep 2026) — matches the executives'
                          Excel sheet, so copy-paste needs no reformatting. */}
                      <TableCell className="whitespace-nowrap text-sm">
                        {formatDateSheet(e.date)}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{e.supplier}</TableCell>
                      <TableCell className="whitespace-nowrap text-sm">{e.supplier_invoice}</TableCell>
                      <TableCell className="whitespace-nowrap text-sm">{e.file_nos}</TableCell>
                      <TableCell className="text-sm">{e.customer}</TableCell>
                      <TableCell className="text-sm">{e.curr}</TableCell>
                      <TableCell />
                      <TableCell />
                      <TableCell className="text-right text-sm tabular-nums">{num(e.amount)}</TableCell>
                      <TableCell />
                      <TableCell />
                    </TableRow>
                  ))
                )}
                {/* Total value per currency — over the whole ledger, not
                    just this page. */}
                {!loading &&
                  totalRows.map(([curr, sum]) => (
                    <TableRow key={`total-${curr}`} className="bg-muted/60 hover:bg-muted/60 font-semibold">
                      <TableCell className="text-sm" colSpan={5}>
                        Total value{totalRows.length > 1 || curr !== "—" ? ` (${curr})` : ""}
                      </TableCell>
                      <TableCell className="text-sm">{curr}</TableCell>
                      <TableCell />
                      <TableCell />
                      <TableCell className="text-right text-sm tabular-nums">{num(sum)}</TableCell>
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

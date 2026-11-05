"use client";

// Bank Ledger tab (4 Sep 2026, executive request): the pending payments
// rendered on screen in the executives' Excel ledger layout — the same
// entries the "Export in Bank Ledger" option downloads, no download needed.
// Voucher No., Rate, Credit and BALANCE are maintained manually in Excel
// (no such data in the system) and render empty here, like the export.

import { useCallback, useEffect, useRef, useState } from "react";
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
  staff:    (e) => e.staff,
  customer: (e) => e.customer,
  curr:     (e) => e.curr,
  debit:    (e) => e.amount,
};

function num(value: number | null): string {
  return value == null
    ? ""
    : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Column widths the user drags are remembered per person, per device
// (5 Nov 2026, executive request). localStorage rather than the server:
// a layout preference should not travel between colleagues.
const WIDTH_STORAGE_KEY = "bank-ledger-column-widths";
const MIN_COL_WIDTH = 70;

function useColumnWidths() {
  const [widths, setWidths] = useState<Record<string, number>>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(WIDTH_STORAGE_KEY);
      if (raw) setWidths(JSON.parse(raw));
    } catch {
      // A blocked or corrupt store just means default widths.
    }
  }, []);

  const persist = useCallback((next: Record<string, number>) => {
    setWidths(next);
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Non-fatal: the drag still applies for this session.
    }
  }, []);

  const reset = useCallback(() => {
    setWidths({});
    try { localStorage.removeItem(WIDTH_STORAGE_KEY); } catch {}
  }, []);

  return { widths, persist, reset };
}

/** The drag handle living on a header's right edge. */
function ColumnResizer({
  colKey,
  widths,
  persist,
}: {
  colKey: string;
  widths: Record<string, number>;
  persist: (next: Record<string, number>) => void;
}) {
  const start = useRef<{ x: number; w: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent<HTMLSpanElement>) => {
    e.preventDefault();
    e.stopPropagation();                     // never triggers the header sort
    const th = (e.currentTarget.closest("th") as HTMLElement | null);
    start.current = { x: e.clientX, w: widths[colKey] ?? th?.offsetWidth ?? 120 };
    const onMove = (ev: PointerEvent) => {
      if (!start.current) return;
      const next = Math.max(MIN_COL_WIDTH, start.current.w + (ev.clientX - start.current.x));
      persist({ ...widths, [colKey]: next });
    };
    const onUp = () => {
      start.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <span
      role="separator"
      aria-label="Resize column"
      onPointerDown={onPointerDown}
      onClick={(e) => e.stopPropagation()}
      className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize select-none hover:bg-background/40"
    />
  );
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
  // Drag-to-resize column widths, remembered per user (5 Nov 2026).
  const { widths, persist, reset } = useColumnWidths();
  const w = (key: string) => (widths[key] ? { width: widths[key] } : undefined);
  const hasCustomWidths = Object.keys(widths).length > 0;
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
          in Excel and stay empty here. Drag any column edge to resize \u2014 your widths
          are remembered on this device.
        </p>
        {hasCustomWidths && (
          <button
            type="button"
            onClick={reset}
            className="mt-2 text-xs text-primary hover:underline underline-offset-2"
          >
            Reset column widths
          </button>
        )}
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
            <Table style={hasCustomWidths ? { tableLayout: "fixed" } : undefined}>
              <TableHeader>
                {/* Dark header band, like the executives' Excel ledger. */}
                <TableRow className="bg-foreground hover:bg-foreground">
                  {/* Asc/desc on every data-bearing header (16 Sep 2026). */}
                  <SortableHead label="Date" sortKey="date" state={colSort} className="text-background whitespace-nowrap" style={w("date")}>
                    <ColumnResizer colKey="date" widths={widths} persist={persist} />
                  </SortableHead>
                  <SortableHead label="Supplier" sortKey="supplier" state={colSort} className="text-background" style={w("supplier")}>
                    <ColumnResizer colKey="supplier" widths={widths} persist={persist} />
                  </SortableHead>
                  <SortableHead label="Supplier Proforma Invoice #" sortKey="proforma" state={colSort} className="text-background whitespace-nowrap" style={w("proforma")}>
                    <ColumnResizer colKey="proforma" widths={widths} persist={persist} />
                  </SortableHead>
                  <SortableHead label="File Nos." sortKey="file_nos" state={colSort} className="text-background whitespace-nowrap" style={w("file_nos")}>
                    <ColumnResizer colKey="file_nos" widths={widths} persist={persist} />
                  </SortableHead>
                  {/* Staff (23 Sep 2026) — the merchandiser who raised the
                      file; data filled in 29 Sep 2026. */}
                  <SortableHead label="Staff" sortKey="staff" state={colSort} className="text-background" style={w("staff")}>
                    <ColumnResizer colKey="staff" widths={widths} persist={persist} />
                  </SortableHead>
                  <SortableHead label="Customer" sortKey="customer" state={colSort} className="text-background" style={w("customer")}>
                    <ColumnResizer colKey="customer" widths={widths} persist={persist} />
                  </SortableHead>
                  <SortableHead label="Curr" sortKey="curr" state={colSort} className="text-background" style={w("curr")}>
                    <ColumnResizer colKey="curr" widths={widths} persist={persist} />
                  </SortableHead>
                  {/* Kept empty for now (client decision, 4 Sep 2026). */}
                  <TableHead className="text-background text-right whitespace-nowrap relative" style={w("euro_cny")}>
                    EURO/CNY
                    <ColumnResizer colKey="euro_cny" widths={widths} persist={persist} />
                  </TableHead>
                  <TableHead className="text-background text-right relative" style={w("rate")}>
                    Rate
                    <ColumnResizer colKey="rate" widths={widths} persist={persist} />
                  </TableHead>
                  <SortableHead label="Debit" sortKey="debit" state={colSort} align="right" className="text-background text-right" style={w("debit")}>
                    <ColumnResizer colKey="debit" widths={widths} persist={persist} />
                  </SortableHead>
                  <TableHead className="text-background text-right relative" style={w("credit")}>
                    Credit
                    <ColumnResizer colKey="credit" widths={widths} persist={persist} />
                  </TableHead>
                  <TableHead className="text-background text-right relative" style={w("balance")}>
                    BALANCE
                    <ColumnResizer colKey="balance" widths={widths} persist={persist} />
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableSkeleton rows={6} cols={12} />
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
                      <TableCell className="text-sm">{e.staff}</TableCell>
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
                      {/* Date → Staff → Customer is now 6 columns. */}
                      <TableCell className="text-sm" colSpan={6}>
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

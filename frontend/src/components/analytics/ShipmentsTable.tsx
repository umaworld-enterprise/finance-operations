"use client";

// Analytical Snapshot — ALL shipments by default (Aug 2026 batch, item 4.2),
// replacing the old single-shipment view. Shared by the HoM and Accounts
// dashboards. Days Delayed is server-computed against today's date.

import Link from "next/link";
import { Ship } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useShipments } from "@/hooks/useAnalytics";
import { TableControls } from "@/components/ui/TableControls";
import { byNumber, byString, useClientTable } from "@/hooks/useClientTable";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { ShipmentRow } from "@/services/analyticsService";
import type { RequestStatus } from "@/types";

function DelayCell({ days }: { days: number | null }) {
  if (days == null) return <span className="text-muted-foreground">—</span>;
  if (days === 0) return <span className="text-emerald-700 text-xs font-medium">On time</span>;
  return (
    <span className={`tabular-nums font-semibold ${days >= 7 ? "text-red-700" : "text-amber-700"}`}>
      {days}d
    </span>
  );
}

const SHIPMENT_SORTS = [
  { value: "delay", label: "Most delayed first", compare: byNumber<ShipmentRow>((s) => s.days_delayed ?? -1, true) },
  { value: "etd", label: "Original ETD", compare: byString<ShipmentRow>((s) => s.estimated_etd ?? "") },
  { value: "amount", label: "Amount (high → low)", compare: byNumber<ShipmentRow>((s) => Number(s.amount), true) },
  { value: "supplier", label: "Supplier (A–Z)", compare: byString<ShipmentRow>((s) => s.supplier_name) },
];

export function ShipmentsTable({ linkBase }: { linkBase: "/hom" | "/accounts" }) {
  const { data: shipments = [], isLoading } = useShipments();
  // Search / sort / pagination (10 Aug 2026, app-wide table controls).
  const table = useClientTable(shipments, {
    searchHaystack: (s) => [
      s.request_number, s.sunshine_invoice_number, s.supplier_name, s.current_status,
    ],
    sortOptions: SHIPMENT_SORTS,
    pageSize: 25,
  });

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3 border-b border-border">
        <CardTitle className="text-sm flex items-center gap-2">
          <Ship className="h-4 w-4" />
          Analytical Snapshot — All Shipments{shipments.length > 0 ? ` (${shipments.length})` : ""}
        </CardTitle>
        <p className="text-xs text-muted-foreground mt-0.5">
          Every live request, most delayed first. Days delayed run from the
          Original ETD to today.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <Table>
            <TableBody><TableSkeleton rows={5} cols={7} /></TableBody>
          </Table>
        ) : shipments.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={Ship}
              title="No shipments"
              description="Live requests will appear here with their ETD and delay."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <div className="px-4 pt-3">
              <TableControls
                search={table.search}
                onSearch={table.setSearch}
                sort={table.sort}
                onSort={table.setSort}
                sortOptions={SHIPMENT_SORTS}
                placeholder="Search by request #, invoice #, supplier or status…"
              />
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Request #</TableHead>
                  <TableHead>Invoice #</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Original ETD</TableHead>
                  <TableHead>Days Delayed</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {table.visible.map((s) => (
                  <TableRow key={s.request_id}>
                    <TableCell>
                      <Link
                        href={`${linkBase}/${s.request_id}`}
                        className="font-mono text-xs font-semibold text-foreground hover:underline underline-offset-2"
                      >
                        {s.request_number}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {s.sunshine_invoice_number || "—"}
                    </TableCell>
                    <TableCell className="text-sm">{s.supplier_name}</TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {formatCurrency(s.amount, s.currency)}
                    </TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {s.estimated_etd ? formatDate(s.estimated_etd) : "—"}
                    </TableCell>
                    <TableCell><DelayCell days={s.days_delayed} /></TableCell>
                    <TableCell>
                      <StatusBadge status={s.current_status as RequestStatus} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {table.totalPages > 1 && (
              <div className="p-4 border-t border-border">
                <Pagination
                  page={table.page}
                  totalPages={table.totalPages}
                  total={table.total}
                  pageSize={table.pageSize}
                  onChange={table.setPage}
                />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

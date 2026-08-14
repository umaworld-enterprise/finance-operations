"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { TableControls } from "@/components/ui/TableControls";
import { byNumber, byString, useClientTable } from "@/hooks/useClientTable";
import { useNpa } from "@/hooks/useAnalytics";
import { formatDate } from "@/lib/utils";
import { AlertTriangle, Bot, User, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";
import type { FlaggedSupplierNpa, MerchandiserNpa } from "@/types";

const SUPPLIER_SORTS = [
  { value: "overdue", label: "Most overdue first", compare: byNumber<FlaggedSupplierNpa>((s) => s.max_overdue_days, true) },
  { value: "requests", label: "Overdue requests (high → low)", compare: byNumber<FlaggedSupplierNpa>((s) => s.overdue_request_count, true) },
  { value: "supplier", label: "Supplier (A–Z)", compare: byString<FlaggedSupplierNpa>((s) => s.supplier_name) },
];

const MERCH_SORTS = [
  { value: "overdue", label: "Most overdue first", compare: byNumber<MerchandiserNpa>((m) => m.overdue_count, true) },
  { value: "requests", label: "Total requests (high → low)", compare: byNumber<MerchandiserNpa>((m) => m.total_requests, true) },
  { value: "name", label: "Name (A–Z)", compare: byString<MerchandiserNpa>((m) => m.name) },
];

export function NpaPanel() {
  const { data, isLoading } = useNpa();

  const flaggedSuppliers = data?.flagged_suppliers ?? [];
  const merchandisers = data?.merchandiser_performance ?? [];

  // Search / sort / pagination (10 Aug 2026, app-wide table controls).
  const supplierTable = useClientTable(flaggedSuppliers, {
    searchHaystack: (s) => [s.supplier_name, s.default_reason],
    sortOptions: SUPPLIER_SORTS,
    pageSize: 10,
  });
  const merchTable = useClientTable(merchandisers, {
    searchHaystack: (m) => [m.name, m.email],
    sortOptions: MERCH_SORTS,
    pageSize: 10,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-32 bg-muted animate-pulse rounded-xl" />
        <div className="h-32 bg-muted animate-pulse rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overdue Suppliers */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Overdue Suppliers ({flaggedSuppliers.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {flaggedSuppliers.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon={AlertTriangle}
                title="No overdue suppliers"
                description="No suppliers are past the ETD grace period."
              />
            </div>
          ) : (
            <>
              <div className="px-4 pt-3">
                <TableControls
                  search={supplierTable.search}
                  onSearch={supplierTable.setSearch}
                  sort={supplierTable.sort}
                  onSort={supplierTable.setSort}
                  sortOptions={SUPPLIER_SORTS}
                  placeholder="Search by supplier or reason…"
                />
              </div>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Supplier</TableHead>
                      <TableHead className="text-right">Max Overdue</TableHead>
                      <TableHead className="text-right">Overdue Requests</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Flagged On</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {supplierTable.visible.map((s) => (
                      <TableRow key={s.supplier_id} className="hover:bg-muted/50 cursor-pointer">
                        <TableCell className="font-medium">{s.supplier_name}</TableCell>
                        <TableCell className="text-right font-semibold text-destructive">
                          {s.max_overdue_days}d
                        </TableCell>
                        <TableCell className="text-right font-semibold">{s.overdue_request_count}</TableCell>
                        <TableCell>
                          {s.is_formally_flagged ? (
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full",
                                s.is_auto_flagged
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-muted text-muted-foreground"
                              )}
                            >
                              {s.is_auto_flagged ? (
                                <><Bot className="h-3 w-3" />Auto-flagged</>
                              ) : (
                                <><User className="h-3 w-3" />Flagged</>
                              )}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-destructive/10 text-destructive">
                              <AlertTriangle className="h-3 w-3" />Overdue
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {s.flagged_date ? formatDate(s.flagged_date) : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                          {s.default_reason ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Link
                            href={`/analytics/supplier/${s.supplier_id}`}
                            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            View <ArrowUpRight className="h-3 w-3" />
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {supplierTable.totalPages > 1 && (
                <div className="p-4 border-t border-border">
                  <Pagination
                    page={supplierTable.page}
                    totalPages={supplierTable.totalPages}
                    total={supplierTable.total}
                    pageSize={supplierTable.pageSize}
                    onChange={supplierTable.setPage}
                  />
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Merchandiser Performance */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <User className="h-4 w-4" />
            Merchandiser Performance ({merchandisers.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {merchandisers.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon={User}
                title="No merchandiser data"
                description="No merchandiser activity to show."
              />
            </div>
          ) : (
            <>
              <div className="px-4 pt-3">
                <TableControls
                  search={merchTable.search}
                  onSearch={merchTable.setSearch}
                  sort={merchTable.sort}
                  onSort={merchTable.setSort}
                  sortOptions={MERCH_SORTS}
                  placeholder="Search by name or email…"
                />
              </div>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Merchandiser</TableHead>
                      <TableHead className="text-right">Total Requests</TableHead>
                      <TableHead className="text-right">Overdue</TableHead>
                      <TableHead className="text-right">Avg Overdue Days</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {merchTable.visible.map((m) => (
                      <TableRow key={m.merchandiser_id} className="hover:bg-muted/50 cursor-pointer">
                        <TableCell>
                          <div>
                            <p className="font-medium text-sm">{m.name}</p>
                            <p className="text-xs text-muted-foreground">{m.email}</p>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">{m.total_requests}</TableCell>
                        <TableCell className="text-right">
                          <span className={cn("font-semibold", m.overdue_count > 0 && "text-destructive")}>
                            {m.overdue_count}
                          </span>
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">
                          {m.avg_overdue_days != null ? `${Math.round(m.avg_overdue_days)}d` : "—"}
                        </TableCell>
                        <TableCell>
                          <Link
                            href={`/analytics/drill?section=by_merchandiser&name=${encodeURIComponent(m.name)}`}
                            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            View <ArrowUpRight className="h-3 w-3" />
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {merchTable.totalPages > 1 && (
                <div className="p-4 border-t border-border">
                  <Pagination
                    page={merchTable.page}
                    totalPages={merchTable.totalPages}
                    total={merchTable.total}
                    pageSize={merchTable.pageSize}
                    onChange={merchTable.setPage}
                  />
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

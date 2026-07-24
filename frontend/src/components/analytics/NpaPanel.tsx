"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { useNpa } from "@/hooks/useAnalytics";
import { formatDate } from "@/lib/utils";
import { AlertTriangle, Bot, User, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

const SUPPLIER_PAGE_SIZE = 10;
const MERCH_PAGE_SIZE = 10;

export function NpaPanel() {
  const { data, isLoading } = useNpa();
  const [supplierPage, setSupplierPage] = useState(1);
  const [merchPage, setMerchPage] = useState(1);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-32 bg-muted animate-pulse rounded-xl" />
        <div className="h-32 bg-muted animate-pulse rounded-xl" />
      </div>
    );
  }

  const flaggedSuppliers = data?.flagged_suppliers ?? [];
  const merchandisers = data?.merchandiser_performance ?? [];

  const supplierTotalPages = Math.ceil(flaggedSuppliers.length / SUPPLIER_PAGE_SIZE);
  const supplierItems = flaggedSuppliers.slice(
    (supplierPage - 1) * SUPPLIER_PAGE_SIZE,
    supplierPage * SUPPLIER_PAGE_SIZE,
  );

  const merchTotalPages = Math.ceil(merchandisers.length / MERCH_PAGE_SIZE);
  const merchItems = merchandisers.slice(
    (merchPage - 1) * MERCH_PAGE_SIZE,
    merchPage * MERCH_PAGE_SIZE,
  );

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
                    {supplierItems.map((s) => (
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
              {supplierTotalPages > 1 && (
                <div className="p-4 border-t border-border">
                  <Pagination
                    page={supplierPage}
                    totalPages={supplierTotalPages}
                    total={flaggedSuppliers.length}
                    pageSize={SUPPLIER_PAGE_SIZE}
                    onChange={setSupplierPage}
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
                    {merchItems.map((m) => (
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
              {merchTotalPages > 1 && (
                <div className="p-4 border-t border-border">
                  <Pagination
                    page={merchPage}
                    totalPages={merchTotalPages}
                    total={merchandisers.length}
                    pageSize={MERCH_PAGE_SIZE}
                    onChange={setMerchPage}
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

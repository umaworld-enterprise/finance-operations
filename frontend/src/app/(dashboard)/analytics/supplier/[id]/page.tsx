"use client";

import { useParams, useRouter } from "next/navigation";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useNpa } from "@/hooks/useAnalytics";
import { useRequestsPaginated } from "@/hooks/useRequests";
import { formatCurrency, formatDate } from "@/lib/utils";
import { AlertTriangle, ArrowLeft, Bot, User, ClipboardList, Calendar, TrendingDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

export default function SupplierDrillPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [page, setPage] = useState(1);

  const { data: npaData, isLoading: npaLoading } = useNpa();
  const supplier = npaData?.flagged_suppliers?.find((s) => s.supplier_id === id);

  const { data: requestsData, isLoading: reqLoading } = useRequestsPaginated(
    page,
    PAGE_SIZE,
    { supplier_id: id },
  );
  const requests = requestsData?.items ?? [];
  const total = requestsData?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const isLoading = npaLoading || reqLoading;

  return (
    <RoleGuard allowedRoles={["super_admin", "head_of_merchandiser", "accounts_team", "finance_admin"]}>
      <TopNav
        title={supplier?.supplier_name ?? requests[0]?.supplier?.name ?? "Supplier Detail"}
        subtitle="Overdue & request history"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-5xl mx-auto w-full">
        <button
          type="button"
          onClick={() => router.back()}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </button>

        {/* Supplier stats */}
        {npaLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />
            ))}
          </div>
        ) : supplier ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <StatCard
                label="Max Overdue"
                value={`${supplier.max_overdue_days}d`}
                icon={TrendingDown}
              />
              <StatCard
                label="Overdue Requests"
                value={supplier.overdue_request_count}
                icon={AlertTriangle}
              />
              <StatCard
                label="Total Requests"
                value={total}
                icon={ClipboardList}
              />
            </div>

            <Card>
              <CardContent className="p-5 md:p-6">
                <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Flagged Status</dt>
                    <dd className="mt-0.5">
                      {supplier.is_formally_flagged ? (
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium",
                            supplier.is_auto_flagged
                              ? "bg-amber-100 text-amber-800"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {supplier.is_auto_flagged ? (
                            <><Bot className="h-3 w-3" /> Auto-flagged</>
                          ) : (
                            <><User className="h-3 w-3" /> Flagged</>
                          )}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-destructive/10 text-destructive font-medium">
                          <AlertTriangle className="h-3 w-3" /> Overdue
                        </span>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Flagged On</dt>
                    <dd className="mt-0.5 font-medium text-foreground text-sm">
                      {supplier.flagged_date ? formatDate(supplier.flagged_date) : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Reason</dt>
                    <dd className="mt-0.5 font-medium text-foreground text-sm">
                      {supplier.default_reason ?? "—"}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </>
        ) : !npaLoading && (
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">
                This supplier is not currently in the overdue list. Showing all requests below.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Requests table */}
        <Card className="overflow-hidden">
          <CardHeader className="pb-3 border-b border-border">
            <CardTitle className="text-sm flex items-center gap-2">
              <ClipboardList className="h-4 w-4" />
              All Requests ({total})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {reqLoading ? (
              <Table>
                <TableBody><TableSkeleton rows={5} cols={6} /></TableBody>
              </Table>
            ) : requests.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={ClipboardList}
                  title="No requests"
                  description="No advance payment requests found for this supplier."
                />
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Request #</TableHead>
                        <TableHead>Customer</TableHead>
                        <TableHead>Vertical</TableHead>
                        <TableHead className="text-right">Deposit</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="hidden lg:table-cell">Submitted</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {requests.map((req) => (
                        <TableRow key={req.id}>
                          <TableCell>
                            <Link
                              href={`/accounts/${req.id}`}
                              className="font-mono text-xs font-semibold text-foreground hover:underline underline-offset-2"
                            >
                              {req.request_number}
                            </Link>
                          </TableCell>
                          <TableCell className="text-foreground">{req.customer.name}</TableCell>
                          <TableCell className="text-muted-foreground text-sm">
                            {req.vertical?.name ?? "—"}
                          </TableCell>
                          <TableCell className="text-right font-semibold">
                            {formatCurrency(req.deposit_amount, req.currency ?? undefined)}
                          </TableCell>
                          <TableCell>
                            <StatusBadge status={req.current_status} showFull />
                          </TableCell>
                          <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">
                            {formatDate(req.created_at)}
                          </TableCell>
                          <TableCell>
                            <Button size="sm" variant="ghost" asChild>
                              <Link href={`/accounts/${req.id}`}>View</Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {totalPages > 1 && (
                  <div className="p-4 border-t border-border">
                    <Pagination
                      page={page}
                      totalPages={totalPages}
                      total={total}
                      pageSize={PAGE_SIZE}
                      onChange={setPage}
                    />
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </RoleGuard>
  );
}

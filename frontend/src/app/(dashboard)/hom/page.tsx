"use client";

import { useState } from "react";
import { Pagination } from "@/components/ui/Pagination";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { NpaPanel } from "@/components/analytics/NpaPanel";
import { ShipmentsTable } from "@/components/analytics/ShipmentsTable";
import { DecisionDialog } from "@/components/hom/DecisionDialog";
import { useHomQueue, useHomApprove, useHomReject } from "@/hooks/useRequests";
import { SearchInput } from "@/components/ui/SearchInput";
import { SortSelect, type RequestSort } from "@/components/ui/SortSelect";
import { formatCurrency, formatDate, requestDisplayNumber, requestMatchesSearch, sortRequests } from "@/lib/utils";
import { toast } from "sonner";
import { Check, X, ClipboardList, UserCog, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import type { DepositRequest } from "@/types";

function HomQueueRow({ req, onApprove, onReject, disabled }: {
  req: DepositRequest;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  disabled: boolean;
}) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/hom/${req.id}`}
          className="font-mono text-xs font-semibold text-foreground hover:underline underline-offset-2"
        >
          {requestDisplayNumber(req)}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {req.sunshine_invoice_number || "—"}
      </TableCell>
      <TableCell>
        <div>
          <p className="font-medium text-sm">{req.supplier.name}</p>
        </div>
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {req.creator?.full_name ?? "—"}
      </TableCell>
      <TableCell className="text-right font-semibold">
        {formatCurrency(req.deposit_amount, req.currency)}
      </TableCell>
      <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
      <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
        {formatDate(req.created_at)}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1" asChild>
            <Link href={`/hom/${req.id}`}>
              <ArrowUpRight className="h-3 w-3" /> View
            </Link>
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2 text-xs gap-1"
            onClick={() => onApprove(req.id)}
            disabled={disabled}
          >
            <Check className="h-3 w-3" /> Approve
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="h-7 px-2 text-xs gap-1"
            onClick={() => onReject(req.id)}
            disabled={disabled}
          >
            <X className="h-3 w-3" /> Reject
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

const PAGE_SIZE = 25;

export default function HomDashboard() {
  const { data: queue = [], isLoading } = useHomQueue();
  const homApprove = useHomApprove();
  const homReject = useHomReject();

  const [approveTarget, setApproveTarget] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<RequestSort>("newest");

  // The HoM queue is a plain array (not server-paginated) — filter/sort client-side.
  const term = search.trim();
  const filtered = sortRequests(
    term ? queue.filter((r) => requestMatchesSearch(r, term)) : queue,
    sort,
  );
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function changeSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function changeSort(value: RequestSort) {
    setSort(value);
    setPage(1);
  }

  const handleApprove = async (remarks: string) => {
    if (!approveTarget) return;
    try {
      await homApprove.mutateAsync({ id: approveTarget, remarks });
      toast.success("Request approved — moved to payment queue.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to approve request.";
      toast.error(msg);
    }
  };

  const handleReject = async (remarks: string) => {
    if (!rejectTarget) return;
    try {
      await homReject.mutateAsync({ id: rejectTarget, remarks });
      toast.success("Request rejected.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reject request.";
      toast.error(msg);
    }
  };

  return (
    <RoleGuard allowedRoles={["head_of_merchandiser", "super_admin"]}>
      <TopNav title="HoM Workspace" subtitle="Head of Merchandiser — approval queue and performance" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">

        {/* Pending Approval Queue */}
        <Card className="overflow-hidden">
          <CardHeader className="pb-3 border-b border-border">
            <CardTitle className="text-sm flex items-center gap-2">
              <UserCog className="h-4 w-4" />
              Pending Approval ({queue.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {!isLoading && queue.length > 0 && (
              <div className="px-4 pt-4 flex flex-col sm:flex-row gap-3">
                <SearchInput
                  value={search}
                  onChange={changeSearch}
                  placeholder="Search by invoice #, request #, supplier or customer…"
                  className="sm:max-w-md flex-1"
                />
                <SortSelect value={sort} onChange={changeSort} className="sm:w-52" />
              </div>
            )}
            {isLoading ? (
              <Table>
                <TableBody><TableSkeleton rows={3} cols={8} /></TableBody>
              </Table>
            ) : queue.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={ClipboardList}
                  title="No pending requests"
                  description="All requests from flagged suppliers have been reviewed."
                />
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={ClipboardList}
                  title="No matching requests"
                  description={`No pending requests match "${term}".`}
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Request #</TableHead>
                      <TableHead>Invoice #</TableHead>
                      <TableHead>Supplier</TableHead>
                      <TableHead>Merchandiser</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="hidden lg:table-cell">Submitted</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageItems.map((req) => (
                      <HomQueueRow
                        key={req.id}
                        req={req}
                        onApprove={(id) => setApproveTarget(id)}
                        onReject={(id) => setRejectTarget(id)}
                        disabled={homApprove.isPending || homReject.isPending}
                      />
                    ))}
                  </TableBody>
                </Table>
                {totalPages > 1 && (
                  <div className="p-4 border-t border-border">
                    <Pagination
                      page={page}
                      totalPages={totalPages}
                      total={filtered.length}
                      pageSize={PAGE_SIZE}
                      onChange={setPage}
                    />
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Analytical Snapshot — all shipments (Aug 2026, item 4.2) */}
        <ShipmentsTable linkBase="/hom" />

        {/* Non-Performing Assets */}
        <div>
          <h2 className="text-sm font-semibold text-foreground mb-3">Non-Performing Assets</h2>
          <NpaPanel />
        </div>

      </main>

      <DecisionDialog
        open={approveTarget !== null}
        title="Approve Request"
        description="Approving moves this request to the accounts payment queue. A reason is mandatory."
        placeholder="Reason for approval"
        confirmLabel="Confirm Approve"
        onClose={() => setApproveTarget(null)}
        onConfirm={handleApprove}
      />
      <DecisionDialog
        open={rejectTarget !== null}
        title="Reject Request"
        description="Rejecting is final for this request. A reason is mandatory — the merchandiser will be notified."
        placeholder="Reason for rejection"
        confirmLabel="Confirm Reject"
        destructive
        onClose={() => setRejectTarget(null)}
        onConfirm={handleReject}
      />
    </RoleGuard>
  );
}

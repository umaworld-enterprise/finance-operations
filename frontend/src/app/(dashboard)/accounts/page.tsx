"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Skeleton } from "@/components/ui/skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { useRequestsPaginated, usePendingQueue, useQueueKpis } from "@/hooks/useRequests";
import { ShipmentsTable } from "@/components/analytics/ShipmentsTable";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { SearchInput } from "@/components/ui/SearchInput";
import { SortSelect, type RequestSort } from "@/components/ui/SortSelect";
import { amountPayable, currencyDisplayLabel, formatCurrency, formatDate, cn, requestDisplayNumber, requestMatchesSearch, sortRequests } from "@/lib/utils";
import { differenceInDays } from "date-fns";
import { Clock, CheckCircle, AlertTriangle, ClipboardList, ArrowRight, XCircle, Ban } from "lucide-react";
import Link from "next/link";
import type { DepositRequest } from "@/types";

const PAGE_SIZE = 50;

function agingBadge(createdAt: string) {
  const days = differenceInDays(new Date(), new Date(createdAt));
  const shade =
    days >= 7 ? "bg-foreground/10 text-foreground border-foreground/20" :
    days >= 3 ? "bg-foreground/5 text-foreground border-foreground/15" :
                "bg-muted text-muted-foreground border-border";
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border", shade)}>
      {days}d waiting
    </span>
  );
}

// Earliest tentative payment date among a request's UNPAID tranches — the
// next money actually going out. Basis for the 0–10 / >10 day split
// (UAT Aug 2026, item 13); undated requests sort as "later".
function nextTentativeDate(req: DepositRequest): string | null {
  const dates = (req.tranches ?? [])
    .filter((t) => t.status === "unpaid" && t.tentative_payment_date)
    .map((t) => t.tentative_payment_date as string)
    .sort();
  return dates[0] ?? null;
}

// Amount Payable in the pending queue counts only the unpaid tranches whose
// tentative date falls within the next 10 days (past-due included) — the
// standing 11 Aug rule, independent of the removed > 10 days table.
function payableDueSoon(req: DepositRequest): number {
  return (req.tranches ?? [])
    .filter((t) => t.status === "unpaid" && t.tentative_payment_date)
    .filter((t) => differenceInDays(new Date(t.tentative_payment_date as string), new Date()) <= 10)
    .reduce((sum, t) => sum + Number(t.amount), 0);
}

function PendingTable({
  rows: allRows,
  loading,
  title,
  subtitle,
}: {
  rows: DepositRequest[];
  loading: boolean;
  title: string;
  subtitle: string;
}) {
  // Each bucket paginates client-side (10 Aug 2026, app-wide table
  // controls) — the page-level search/sort apply before the split.
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(allRows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rows = allRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground text-sm">{title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        {allRows.length > 0 && (
          <span className="text-xs text-muted-foreground font-medium">{allRows.length} awaiting</span>
        )}
      </div>

      {/* Mobile card list */}
      <div className="md:hidden divide-y divide-border">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="p-4 space-y-2.5">
                <div className="flex items-start justify-between gap-3">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3.5 w-32" />
                <div className="flex items-center justify-between">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-8 w-24 rounded-md" />
                </div>
              </div>
            ))}
          </>
        ) : rows.length === 0 ? (
          <EmptyState icon={CheckCircle} title="Queue is clear" description="No pending payments in this bucket." />
        ) : rows.map((req) => (
          <div key={req.id} className="p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              {agingBadge(req.created_at)}
            </div>
            <div className="text-xs text-muted-foreground font-mono">Invoice # {req.sunshine_invoice_number || "—"}</div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
            <div className="text-xs text-muted-foreground">
              {req.vertical?.name ?? "—"} · {req.creator?.full_name ?? "—"}
            </div>
            <div className="text-xs text-muted-foreground">
              Tentative payment: {formatDate(nextTentativeDate(req))}
            </div>
            <div className="text-xs text-muted-foreground">
              Payable (0–10 days): <span className="font-semibold text-foreground">{formatCurrency(payableDueSoon(req), req.currency)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</span>
              <Button size="sm" asChild>
                <Link href={`/accounts/${req.id}`} className="gap-1.5">
                  Process <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Vertical/Category</TableHead>
              <TableHead>Merchandiser</TableHead>
              <TableHead className="text-right">Amount Payable (0–10 days)</TableHead>
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Currency</TableHead>
              <TableHead>Tentative Payment</TableHead>
              <TableHead>Waiting</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableSkeleton rows={5} cols={12} />
            ) : rows.length === 0 ? (
              <tr><td colSpan={12}><EmptyState icon={CheckCircle} title="Queue is clear" description="No pending payments in this bucket." /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                <TableCell className="text-muted-foreground text-xs">{req.vertical?.name ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground text-xs">{req.creator?.full_name ?? "—"}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(payableDueSoon(req), req.currency)}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell className="text-muted-foreground text-xs font-medium">{currencyDisplayLabel(req.currency)}</TableCell>
                <TableCell className="text-muted-foreground text-xs whitespace-nowrap">{formatDate(nextTentativeDate(req))}</TableCell>
                <TableCell>{agingBadge(req.created_at)}</TableCell>
                <TableCell>
                  <Button size="sm" asChild>
                    <Link href={`/accounts/${req.id}`} className="gap-1.5">Process <ArrowRight className="h-3 w-3" /></Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {allRows.length > PAGE_SIZE && (
        <div className="px-5">
          <Pagination
            page={safePage}
            totalPages={totalPages}
            total={allRows.length}
            pageSize={PAGE_SIZE}
            onChange={setPage}
          />
        </div>
      )}
    </Card>
  );
}

// A merchandiser-held or merchandiser-cancelled request is frozen for
// Accounts (UAT Aug 2026, item 7): greyed, non-clickable, notification
// purposes only. The backend refuses accounts writes on them regardless.
function frozenForAccounts(req: DepositRequest): boolean {
  return (
    req.current_status === "hold_by_merchandiser" ||
    req.current_status === "cancelled_by_merchandiser"
  );
}

// Shared table for the status-scoped tabs (On Hold / Rejected / Cancelled —
// UAT Aug 2026, items 17 & 19: rejected and cancelled requests live under
// their own heads, never in Pending).
function StatusTable({
  rows,
  title,
  subtitle,
  emptyTitle,
  showPayable = false,
}: {
  rows: DepositRequest[];
  title: string;
  subtitle: string;
  emptyTitle: string;
  /** Show the Amount Payable column — meaningful for live requests (On
   * Hold), noise for closed ones (Rejected/Cancelled). */
  showPayable?: boolean;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-foreground text-sm">{title}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
      </div>

      {/* Mobile card list */}
      <div className="md:hidden divide-y divide-border">
        {rows.length === 0 ? (
          <EmptyState icon={AlertTriangle} title={emptyTitle} />
        ) : rows.map((req) => (
          <div key={req.id} className={cn("p-4 space-y-2.5", frozenForAccounts(req) && "opacity-50")}>
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              <StatusBadge status={req.current_status} showFull />
            </div>
            <div className="text-xs text-muted-foreground font-mono">Invoice # {req.sunshine_invoice_number || "—"}</div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
            {req.last_status_change_by && (
              <div className="text-xs text-muted-foreground">By {req.last_status_change_by}</div>
            )}
            {showPayable && (
              <div className="text-xs text-muted-foreground">
                Payable: <span className="font-semibold text-foreground">{formatCurrency(amountPayable(req), req.currency)}</span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</span>
              {frozenForAccounts(req) ? (
                <span className="text-xs text-muted-foreground italic">Locked by merchandiser</span>
              ) : (
                <Button size="sm" variant="outline" asChild>
                  <Link href={`/accounts/${req.id}`}>View</Link>
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Customer</TableHead>
              {showPayable && <TableHead className="text-right">Amount Payable</TableHead>}
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>By</TableHead>
              <TableHead className="hidden lg:table-cell">Submitted</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <tr><td colSpan={showPayable ? 10 : 9}><EmptyState icon={AlertTriangle} title={emptyTitle} /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id} className={cn(frozenForAccounts(req) && "opacity-50 pointer-events-none select-none")}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                {showPayable && (
                  <TableCell className="text-right font-semibold text-foreground">{formatCurrency(amountPayable(req), req.currency)}</TableCell>
                )}
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
                <TableCell className="text-muted-foreground text-xs">{req.last_status_change_by ?? "—"}</TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{formatDate(req.created_at)}</TableCell>
                <TableCell>
                  {frozenForAccounts(req) ? (
                    <span className="text-xs text-muted-foreground italic whitespace-nowrap">Locked</span>
                  ) : (
                    <Button size="sm" variant="outline" asChild><Link href={`/accounts/${req.id}`}>View</Link></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

function AllTable({ rows }: { rows: DepositRequest[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-foreground text-sm">All Requests</h3>
      </div>

      {/* Mobile card list */}
      <div className="md:hidden divide-y divide-border">
        {rows.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No requests yet" />
        ) : rows.map((req) => (
          <div key={req.id} className={cn("p-4 space-y-2.5", frozenForAccounts(req) && "opacity-50")}>
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              <StatusBadge status={req.current_status} showFull />
            </div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
            <div className="text-xs text-muted-foreground">
              Payable: <span className="font-semibold text-foreground">{formatCurrency(amountPayable(req), req.currency)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</span>
              {frozenForAccounts(req) ? (
                <span className="text-xs text-muted-foreground italic">Locked by merchandiser</span>
              ) : (
                <Button size="sm" variant="ghost" asChild>
                  <Link href={`/accounts/${req.id}`}>View</Link>
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead className="text-right">Amount Payable</TableHead>
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden lg:table-cell">Submitted</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <tr><td colSpan={9}><EmptyState icon={ClipboardList} title="No requests yet" /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id} className={cn(frozenForAccounts(req) && "opacity-50 pointer-events-none select-none")}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(amountPayable(req), req.currency)}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{formatDate(req.created_at)}</TableCell>
                <TableCell>
                  {frozenForAccounts(req) ? (
                    <span className="text-xs text-muted-foreground italic whitespace-nowrap">Locked</span>
                  ) : (
                    <Button size="sm" variant="ghost" asChild><Link href={`/accounts/${req.id}`}>View</Link></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

export default function AccountsDashboard() {
  const [holdPage, setHoldPage] = useState(1);
  const [rejectedPage, setRejectedPage] = useState(1);
  const [cancelledPage, setCancelledPage] = useState(1);
  const [allPage, setAllPage]   = useState(1);
  const [activeTab, setActiveTab] = useState("pending");
  const [search, setSearch]     = useState("");
  // null = untouched: the pending queue keeps its designed oldest-first order
  // ("process in order") until the user actively picks a sort.
  const [sort, setSort]         = useState<RequestSort | null>(null);
  const debouncedSearch = useDebouncedValue(search.trim());
  const listParams = {
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(sort && sort !== "newest" ? { sort } : {}),
  };

  const { data: queue = [], isLoading: queueLoading } = usePendingQueue();
  // Pending queue is a plain array (not server-paginated) — filter/sort
  // client-side on the raw input so it feels instant.
  const term = search.trim();
  let filteredQueue = term ? queue.filter((r) => requestMatchesSearch(r, term)) : queue;
  if (sort) filteredQueue = sortRequests(filteredQueue, sort);

  const { data: holdData, isLoading: holdLoading } = useRequestsPaginated(holdPage, PAGE_SIZE, {
    status: ["hold_by_accounts", "hold_by_merchandiser"],
    ...listParams,
  });
  // Rejected and cancelled get their own heads — never mixed into Pending
  // (UAT Aug 2026, items 17 & 19).
  const { data: rejectedData, isLoading: rejectedLoading } = useRequestsPaginated(rejectedPage, PAGE_SIZE, {
    status: ["rejected_by_accounts", "rejected_by_hom"],
    ...listParams,
  });
  const { data: cancelledData, isLoading: cancelledLoading } = useRequestsPaginated(cancelledPage, PAGE_SIZE, {
    status: ["cancelled_by_merchandiser", "cancelled_by_accounts"],
    ...listParams,
  });
  const { data: allData, isLoading: allLoading } = useRequestsPaginated(allPage, PAGE_SIZE, listParams);

  // KPI cards: financial-year-to-date (April–March), one backend query
  // (UAT Aug 2026, item 5).
  const { data: kpis } = useQueueKpis();

  function changeSearch(value: string) {
    setSearch(value);
    setHoldPage(1);
    setRejectedPage(1);
    setCancelledPage(1);
    setAllPage(1);
  }

  function changeSort(value: RequestSort) {
    setSort(value);
    setHoldPage(1);
    setRejectedPage(1);
    setCancelledPage(1);
    setAllPage(1);
  }

  const holdItems = holdData?.items ?? [];
  const holdTotal = holdData?.total ?? 0;
  const holdTotalPages = Math.ceil(holdTotal / PAGE_SIZE);

  const rejectedItems = rejectedData?.items ?? [];
  const rejectedTotal = rejectedData?.total ?? 0;
  const rejectedTotalPages = Math.ceil(rejectedTotal / PAGE_SIZE);

  const cancelledItems = cancelledData?.items ?? [];
  const cancelledTotal = cancelledData?.total ?? 0;
  const cancelledTotalPages = Math.ceil(cancelledTotal / PAGE_SIZE);

  const allItems = allData?.items ?? [];
  const allTotal = allData?.total ?? 0;
  const allTotalPages = Math.ceil(allTotal / PAGE_SIZE);

  // Label refinement (10 Aug): plain "YTD", not "FY 2026–27 to date".
  const fySubtext = "YTD";

  return (
    <RoleGuard allowedRoles={["accounts_team", "super_admin"]}>
      <TopNav
        title="Payment Queue"
        subtitle="Process advance deposit payments in order of submission"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        {/* FY-to-date KPIs (April–March), incl. Rejected and Cancelled heads
            (UAT Aug 2026, items 5, 17, 19). */}
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <StatCard
            label="Pending Payment"
            value={kpis?.pending_payment ?? queue.length}
            icon={Clock}
            subtext={fySubtext}
          />
          <StatCard
            label="On Hold"
            value={kpis?.on_hold ?? "—"}
            icon={AlertTriangle}
            subtext={fySubtext}
          />
          <StatCard
            label="Processed"
            value={kpis?.processed ?? "—"}
            icon={CheckCircle}
            subtext={fySubtext}
          />
          <StatCard
            label="Rejected"
            value={kpis?.rejected ?? "—"}
            icon={XCircle}
            subtext={fySubtext}
          />
          <StatCard
            label="Cancelled"
            value={kpis?.cancelled ?? "—"}
            icon={Ban}
            subtext={fySubtext}
          />
          <StatCard
            label="Total Requests"
            value={kpis?.total ?? "—"}
            icon={ClipboardList}
            subtext={fySubtext}
          />
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <SearchInput
            value={search}
            onChange={changeSearch}
            placeholder="Search by invoice #, request #, supplier or customer…"
            className="sm:max-w-md flex-1"
          />
          {/* Until touched, the label mirrors each tab's real default order:
              pending is served oldest-first ("process in order"), the rest newest-first. */}
          <SortSelect
            value={sort ?? (activeTab === "pending" ? "oldest" : "newest")}
            onChange={changeSort}
            className="sm:w-52"
          />
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-1">
            <TabsTrigger value="pending">
              Pending
              {filteredQueue.length > 0 && (
                <span className="ml-1.5 bg-primary text-primary-foreground text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {filteredQueue.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="hold">
              On Hold
              {holdTotal > 0 && (
                <span className="ml-1.5 bg-secondary text-secondary-foreground border border-border text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {holdTotal}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="rejected">
              Rejected
              {rejectedTotal > 0 && (
                <span className="ml-1.5 bg-secondary text-secondary-foreground border border-border text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {rejectedTotal}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="cancelled">
              Cancelled
              {cancelledTotal > 0 && (
                <span className="ml-1.5 bg-secondary text-secondary-foreground border border-border text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {cancelledTotal}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="all">All Requests</TabsTrigger>
          </TabsList>

          <TabsContent value="pending">
            {/* Single pending table (11 Aug — the > 10 days split was
                removed); the Tentative Payment column carries the date. */}
            <PendingTable
              rows={filteredQueue}
              loading={queueLoading}
              title="Pending Payment"
              subtitle="Sorted oldest first — the Tentative Payment column shows each file's next due date"
            />
          </TabsContent>

          <TabsContent value="hold">
            {holdLoading ? (
              <Card className="overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Request #</TableHead><TableHead>Invoice #</TableHead>
                      <TableHead>Supplier</TableHead><TableHead>Customer</TableHead>
                      <TableHead>Deposit</TableHead><TableHead>Status</TableHead><TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody><TableSkeleton rows={5} cols={7} /></TableBody>
                </Table>
              </Card>
            ) : (
              <>
                <StatusTable
                  rows={holdItems}
                  title="On Hold"
                  subtitle="Requests placed on hold"
                  emptyTitle="No requests on hold"
                  showPayable
                />
                <Pagination
                  page={holdPage}
                  totalPages={holdTotalPages}
                  total={holdTotal}
                  pageSize={PAGE_SIZE}
                  onChange={setHoldPage}
                />
              </>
            )}
          </TabsContent>

          <TabsContent value="rejected">
            {rejectedLoading ? (
              <Card className="overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Request #</TableHead><TableHead>Invoice #</TableHead>
                      <TableHead>Supplier</TableHead><TableHead>Customer</TableHead>
                      <TableHead>Deposit</TableHead><TableHead>Status</TableHead><TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody><TableSkeleton rows={5} cols={7} /></TableBody>
                </Table>
              </Card>
            ) : (
              <>
                <StatusTable
                  rows={rejectedItems}
                  title="Rejected"
                  subtitle="Rejected by Accounts or Head of Merchandiser — terminal; invoice numbers are reusable"
                  emptyTitle="No rejected requests"
                />
                <Pagination
                  page={rejectedPage}
                  totalPages={rejectedTotalPages}
                  total={rejectedTotal}
                  pageSize={PAGE_SIZE}
                  onChange={setRejectedPage}
                />
              </>
            )}
          </TabsContent>

          <TabsContent value="cancelled">
            {cancelledLoading ? (
              <Card className="overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Request #</TableHead><TableHead>Invoice #</TableHead>
                      <TableHead>Supplier</TableHead><TableHead>Customer</TableHead>
                      <TableHead>Deposit</TableHead><TableHead>Status</TableHead><TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody><TableSkeleton rows={5} cols={7} /></TableBody>
                </Table>
              </Card>
            ) : (
              <>
                <StatusTable
                  rows={cancelledItems}
                  title="Cancelled"
                  subtitle="Cancelled by the merchandiser or Accounts"
                  emptyTitle="No cancelled requests"
                />
                <Pagination
                  page={cancelledPage}
                  totalPages={cancelledTotalPages}
                  total={cancelledTotal}
                  pageSize={PAGE_SIZE}
                  onChange={setCancelledPage}
                />
              </>
            )}
          </TabsContent>

          <TabsContent value="all">
            {allLoading ? (
              <Card className="overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Request #</TableHead><TableHead>Invoice #</TableHead>
                      <TableHead>Supplier</TableHead><TableHead>Customer</TableHead>
                      <TableHead>Deposit</TableHead><TableHead>Status</TableHead><TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody><TableSkeleton rows={5} cols={7} /></TableBody>
                </Table>
              </Card>
            ) : (
              <>
                <AllTable rows={allItems} />
                <Pagination
                  page={allPage}
                  totalPages={allTotalPages}
                  total={allTotal}
                  pageSize={PAGE_SIZE}
                  onChange={setAllPage}
                />
              </>
            )}
          </TabsContent>
        </Tabs>

        {/* Analytical Snapshot — all shipments (Aug 2026, item 4.2) */}
        <ShipmentsTable linkBase="/accounts" />
      </main>
    </RoleGuard>
  );
}

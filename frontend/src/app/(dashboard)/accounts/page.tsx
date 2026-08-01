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
import { useRequestsPaginated, usePendingQueue } from "@/hooks/useRequests";
import { ShipmentsTable } from "@/components/analytics/ShipmentsTable";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { SearchInput } from "@/components/ui/SearchInput";
import { SortSelect, type RequestSort } from "@/components/ui/SortSelect";
import { currencyDisplayLabel, formatCurrency, formatDate, cn, requestDisplayNumber, requestMatchesSearch, sortRequests } from "@/lib/utils";
import { differenceInDays } from "date-fns";
import { Clock, CheckCircle, AlertTriangle, ClipboardList, ArrowRight } from "lucide-react";
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

function PendingTable({ rows, loading }: { rows: DepositRequest[]; loading: boolean }) {
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground text-sm">Pending Payment</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Sorted oldest first — process in order</p>
        </div>
        {rows.length > 0 && (
          <span className="text-xs text-muted-foreground font-medium">{rows.length} awaiting</span>
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
          <EmptyState icon={CheckCircle} title="Queue is clear" description="All pending payments have been processed." />
        ) : rows.map((req) => (
          <div key={req.id} className="p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              {agingBadge(req.created_at)}
            </div>
            <div className="text-xs text-muted-foreground font-mono">Invoice # {req.sunshine_invoice_number || "—"}</div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
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
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Currency</TableHead>
              <TableHead>Waiting</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableSkeleton rows={5} cols={8} />
            ) : rows.length === 0 ? (
              <tr><td colSpan={8}><EmptyState icon={CheckCircle} title="Queue is clear" description="All pending payments have been processed." /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell className="text-muted-foreground text-xs font-medium">{currencyDisplayLabel(req.currency)}</TableCell>
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
    </Card>
  );
}

function HoldTable({ rows }: { rows: DepositRequest[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-foreground text-sm">On Hold</h3>
        <p className="text-xs text-muted-foreground mt-0.5">Requests placed on hold</p>
      </div>

      {/* Mobile card list */}
      <div className="md:hidden divide-y divide-border">
        {rows.length === 0 ? (
          <EmptyState icon={AlertTriangle} title="No requests on hold" />
        ) : rows.map((req) => (
          <div key={req.id} className="p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              <StatusBadge status={req.current_status} showFull />
            </div>
            <div className="text-xs text-muted-foreground font-mono">Invoice # {req.sunshine_invoice_number || "—"}</div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</span>
              <Button size="sm" variant="outline" asChild>
                <Link href={`/accounts/${req.id}`}>View</Link>
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
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden lg:table-cell">Submitted</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <tr><td colSpan={8}><EmptyState icon={AlertTriangle} title="No requests on hold" /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{formatDate(req.created_at)}</TableCell>
                <TableCell><Button size="sm" variant="outline" asChild><Link href={`/accounts/${req.id}`}>View</Link></Button></TableCell>
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
          <div key={req.id} className="p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-xs font-bold text-foreground">{requestDisplayNumber(req)}</span>
              <StatusBadge status={req.current_status} showFull />
            </div>
            <div className="text-sm font-semibold text-foreground">{req.supplier.name}</div>
            <div className="text-xs text-muted-foreground">{req.customer.name}</div>
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</span>
              <Button size="sm" variant="ghost" asChild>
                <Link href={`/accounts/${req.id}`}>View</Link>
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
              <TableHead className="text-right">Deposit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden lg:table-cell">Submitted</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <tr><td colSpan={8}><EmptyState icon={ClipboardList} title="No requests yet" /></td></tr>
            ) : rows.map((req) => (
              <TableRow key={req.id}>
                <TableCell><span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
                <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
                <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
                <TableCell className="text-right font-semibold text-foreground">{formatCurrency(req.deposit_amount, req.currency)}</TableCell>
                <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{formatDate(req.created_at)}</TableCell>
                <TableCell><Button size="sm" variant="ghost" asChild><Link href={`/accounts/${req.id}`}>View</Link></Button></TableCell>
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
  const { data: allData, isLoading: allLoading } = useRequestsPaginated(allPage, PAGE_SIZE, listParams);

  // Pre-fetch for stat card counts (always global — unaffected by search)
  const { data: processedData } = useRequestsPaginated(1, 1, { status: "payment_processed" });
  const { data: statHoldData }  = useRequestsPaginated(1, 1, { status: ["hold_by_accounts", "hold_by_merchandiser"] });
  const { data: statAllData }   = useRequestsPaginated(1, 1, {});

  function changeSearch(value: string) {
    setSearch(value);
    setHoldPage(1);
    setAllPage(1);
  }

  function changeSort(value: RequestSort) {
    setSort(value);
    setHoldPage(1);
    setAllPage(1);
  }

  const holdItems = holdData?.items ?? [];
  const holdTotal = holdData?.total ?? 0;
  const holdTotalPages = Math.ceil(holdTotal / PAGE_SIZE);

  const allItems = allData?.items ?? [];
  const allTotal = allData?.total ?? 0;
  const allTotalPages = Math.ceil(allTotal / PAGE_SIZE);

  return (
    <RoleGuard allowedRoles={["accounts_team", "super_admin"]}>
      <TopNav
        title="Payment Queue"
        subtitle="Process advance deposit payments in order of submission"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Pending Payment"
            value={queue.length}
            icon={Clock}
            subtext="Awaiting processing"
          />
          <StatCard
            label="On Hold"
            value={statHoldData?.total ?? "—"}
            icon={AlertTriangle}
            subtext="Needs attention"
          />
          <StatCard
            label="Processed"
            value={processedData?.total ?? "—"}
            icon={CheckCircle}
            subtext="This period"
          />
          <StatCard
            label="Total Requests"
            value={statAllData?.total ?? "—"}
            icon={ClipboardList}
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
            <TabsTrigger value="all">All Requests</TabsTrigger>
          </TabsList>

          <TabsContent value="pending">
            <PendingTable rows={filteredQueue} loading={queueLoading} />
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
                <HoldTable rows={holdItems} />
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

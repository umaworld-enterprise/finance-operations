"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { useRequestsPaginated } from "@/hooks/useRequests";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { SearchInput } from "@/components/ui/SearchInput";
import { SortSelect, type RequestSort } from "@/components/ui/SortSelect";
import { useUsers } from "@/hooks/useMasters";
import { useAnalyticsSummary, useAnalyticsSnapshots } from "@/hooks/useAnalytics";
import { NpaPanel } from "@/components/analytics/NpaPanel";
import { formatCurrency, formatDate, requestDisplayNumber } from "@/lib/utils";
import {
  Users, ClipboardList, TrendingUp, AlertTriangle, ArrowUpRight,
  LayoutDashboard, ScrollText, BarChart3, ShieldCheck, Eye, Landmark, ListChecks,
} from "lucide-react";
import Link from "next/link";
import type { DepositRequest } from "@/types";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
type PageSizeOption = typeof PAGE_SIZE_OPTIONS[number];

const TAB_PARAMS: Record<"all" | "pending" | "processed" | "cancelled", Record<string, string | string[]>> = {
  all:       {},
  pending:   { status: "pending_payment" },
  processed: { status: "payment_processed" },
  cancelled: { status: ["cancelled_by_merchandiser", "cancelled_by_accounts"] },
};
type Tab = keyof typeof TAB_PARAMS;

// Form Configuration and Form Links were removed when the public (login-free)
// request form was retired (Aug 2026) — the pages still exist by direct URL
// with a deprecation banner, but are no longer part of the admin workflow.
const QUICK_LINKS = [
  { label: "Manage Users",      href: "/admin/users",             desc: "Add, edit, assign roles",                                     icon: Users },
  { label: "Audit Logs",        href: "/admin/audit",             desc: "Full field-level change trail",                               icon: ScrollText },
  { label: "Analytics",         href: "/analytics",               desc: "Metrics & cost of fund",                                      icon: BarChart3 },
  { label: "Analytics Access",  href: "/admin/analytics-access",  desc: "Control which roles see which analytics sections",            icon: ShieldCheck },
  { label: "Field Visibility",  href: "/admin/field-visibility",  desc: "Control which columns each role sees in request details",     icon: Eye },
  { label: "Payment Terms",     href: "/admin/payment-terms",     desc: "Manage the payment terms available in request forms",         icon: ListChecks },
  { label: "Banks",             href: "/admin/banks",             desc: "Bank names for the tranche payment dropdown",                 icon: Landmark },
];

function RequestRow({ req }: { req: DepositRequest }) {
  return (
    <TableRow>
      <TableCell>
        <span className="font-mono text-xs text-foreground font-semibold">{requestDisplayNumber(req)}</span>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number || "—"}</TableCell>
      <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
      <TableCell className="hidden md:table-cell text-muted-foreground">{req.customer.name}</TableCell>
      <TableCell className="text-right font-semibold text-foreground">
        {formatCurrency(req.deposit_amount, req.currency)}
      </TableCell>
      <TableCell><StatusBadge status={req.current_status} showFull /></TableCell>
      <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{formatDate(req.created_at)}</TableCell>
      <TableCell>
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/accounts/${req.id}`} aria-label={`View request ${req.request_number}`}>
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}

export default function AdminDashboard() {
  const [tab, setTab]           = useState<Tab>("all");
  const [page, setPage]         = useState(1);
  const [pageSize, setPageSize] = useState<PageSizeOption>(25);
  const [search, setSearch]     = useState("");
  const [sort, setSort]         = useState<RequestSort>("newest");
  const debouncedSearch = useDebouncedValue(search.trim());

  // Main table
  const { data, isLoading, isFetching } = useRequestsPaginated(page, pageSize, {
    ...TAB_PARAMS[tab],
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(sort !== "newest" ? { sort } : {}),
  });
  const items      = data?.items ?? [];
  const total      = data?.total ?? 0;
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  // Tab badge counts (page_size=1 — we only need the total)
  const { data: allCount }       = useRequestsPaginated(1, 1, TAB_PARAMS.all);
  const { data: pendingCount }   = useRequestsPaginated(1, 1, TAB_PARAMS.pending);
  const { data: processedCount } = useRequestsPaginated(1, 1, TAB_PARAMS.processed);
  const { data: cancelledCount } = useRequestsPaginated(1, 1, TAB_PARAMS.cancelled);

  const { data: users = [] }  = useUsers();
  const { data: summary }     = useAnalyticsSummary();
  const { data: snapshots = [] } = useAnalyticsSnapshots();
  const criticalSnaps = snapshots.filter((s) => s.default_status === "critical");

  function changeTab(t: Tab) {
    setTab(t);
    setPage(1);
  }

  function changePageSize(size: PageSizeOption) {
    setPageSize(size);
    setPage(1);
  }

  function changeSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function changeSort(value: RequestSort) {
    setSort(value);
    setPage(1);
  }

  const TABLE_HEADER = (
    <TableHeader>
      <TableRow>
        <TableHead>Request #</TableHead>
        <TableHead>Invoice #</TableHead>
        <TableHead>Supplier</TableHead>
        <TableHead className="hidden md:table-cell">Customer</TableHead>
        <TableHead className="text-right">Deposit</TableHead>
        <TableHead>Status</TableHead>
        <TableHead className="hidden lg:table-cell">Submitted</TableHead>
        <TableHead />
      </TableRow>
    </TableHeader>
  );

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="Admin Overview" subtitle="System-wide overview and administration" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">

        {/* Stat cards — the first three drill into searchable lists */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Requests"    value={allCount?.total ?? "—"}                        icon={ClipboardList} href="#all-requests" />
          <StatCard label="Active Users"      value={users.filter((u) => u.is_active).length}       icon={Users} href="/admin/users" />
          <StatCard label="Overdue Shipments" value={summary?.overdue_shipments ?? 0}               icon={AlertTriangle} href="/analytics/drill?section=shipment_kpis&filter=overdue" />
          <StatCard label="Cost of Fund"      value={formatCurrency(summary?.total_cost_of_fund ?? 0, "USD")} icon={TrendingUp} />
        </div>

        {/* Quick links */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {QUICK_LINKS.map(({ label, href, desc, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group bg-card rounded-xl border border-border shadow-sm p-5 hover:border-foreground/30 hover:shadow-md transition-all flex items-start gap-4"
            >
              <div className="bg-muted p-2.5 rounded-lg group-hover:bg-accent transition-colors">
                <Icon className="h-4 w-4 text-foreground" />
              </div>
              <div>
                <p className="font-semibold text-foreground text-sm">{label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
              </div>
            </Link>
          ))}
        </div>

        {/* Critical alert */}
        {criticalSnaps.length > 0 && (
          <Card className="border-foreground/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Critical Overdue Shipments ({criticalSnaps.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {criticalSnaps.slice(0, 5).map((s) => (
                  <li key={s.deposit_request_id}>
                    <Link
                      href={`/accounts/${s.deposit_request_id}`}
                      className="flex items-center justify-between text-sm hover:bg-muted/50 rounded-md px-2 py-1 -mx-2 transition-colors"
                    >
                      <span className="font-mono text-foreground font-semibold text-xs">
                        {s.request_number ?? s.deposit_request_id?.slice(0, 8)}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-foreground font-semibold">{s.etd_grace_overdue_days}d overdue</span>
                        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* Non-Performing Assets */}
        <div>
          <h2 className="text-sm font-semibold text-foreground mb-3">Non-Performing Assets</h2>
          <NpaPanel />
        </div>

        {/* Requests table */}
        <Card id="all-requests" className="overflow-hidden scroll-mt-6">
          <div className="px-5 py-4 border-b border-border flex items-center gap-3">
            <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
            <span className="font-semibold text-foreground text-sm">All Requests</span>
          </div>

          <div className="p-4 space-y-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <SearchInput
                value={search}
                onChange={changeSearch}
                placeholder="Search by invoice #, request #, supplier or customer…"
                className="sm:max-w-md flex-1"
              />
              <SortSelect value={sort} onChange={changeSort} className="sm:w-52" />
            </div>

            {/* Tab bar + page size selector */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs value={tab} onValueChange={(v) => changeTab(v as Tab)}>
                <TabsList>
                  <TabsTrigger value="all">All ({allCount?.total ?? "…"})</TabsTrigger>
                  <TabsTrigger value="pending">Pending ({pendingCount?.total ?? "…"})</TabsTrigger>
                  <TabsTrigger value="processed">Processed ({processedCount?.total ?? "…"})</TabsTrigger>
                  <TabsTrigger value="cancelled">Cancelled ({cancelledCount?.total ?? "…"})</TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Rows per page</span>
                <select
                  value={pageSize}
                  onChange={(e) => changePageSize(Number(e.target.value) as PageSizeOption)}
                  className="rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Table */}
            <div className={`transition-opacity ${isFetching && !isLoading ? "opacity-60" : "opacity-100"}`}>
              {isLoading ? (
                <Table>
                  {TABLE_HEADER}
                  <TableBody><TableSkeleton rows={pageSize > 25 ? 10 : 5} cols={8} /></TableBody>
                </Table>
              ) : items.length === 0 ? (
                <EmptyState icon={ClipboardList} title="No requests" description="No requests match this filter." />
              ) : (
                <Table>
                  {TABLE_HEADER}
                  <TableBody>
                    {items.map((req) => <RequestRow key={req.id} req={req} />)}
                  </TableBody>
                </Table>
              )}
            </div>

            <Pagination
              page={page}
              totalPages={totalPages}
              total={total}
              pageSize={pageSize}
              onChange={setPage}
            />
          </div>
        </Card>

      </main>
    </RoleGuard>
  );
}

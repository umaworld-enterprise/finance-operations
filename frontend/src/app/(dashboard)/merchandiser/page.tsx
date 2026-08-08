"use client";

import { useEffect, useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { NewRequestForm } from "@/components/forms/NewRequestForm";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Pagination } from "@/components/ui/Pagination";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RequestsTable } from "@/components/tables/RequestsTable";
import { SearchInput } from "@/components/ui/SearchInput";
import { SortSelect, type RequestSort } from "@/components/ui/SortSelect";
import { useRequestsPaginated, useMyActivity } from "@/hooks/useRequests";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  Table, TableHeader, TableBody, TableRow, TableHead,
} from "@/components/ui/table";
import { ClipboardList, Clock, CheckCircle, XCircle, Bell, ArrowRight, Plus, ChevronDown } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { timeAgo } from "@/lib/utils";
import type { RequestStatus } from "@/types";

const PAGE_SIZE = 50;

const STATUS_BORDER: Record<RequestStatus, string> = {
  pending_payment: "border-l-amber-500",
  pending_hom_approval: "border-l-amber-500",
  hold_by_merchandiser: "border-l-orange-500",
  hold_by_accounts: "border-l-orange-500",
  payment_processed: "border-l-green-500",
  cancelled_by_merchandiser: "border-l-red-500",
  cancelled_by_accounts: "border-l-red-500",
  rejected_by_hom: "border-l-red-500",
  rejected_by_accounts: "border-l-red-500",
  reopened: "border-l-blue-500",
};

const TAB_PARAMS: Record<string, Record<string, string | string[]>> = {
  all:       {},
  pending:   { status: "pending_payment" },
  hold:      { status: ["hold_by_merchandiser", "hold_by_accounts"] },
  processed: { status: "payment_processed" },
  cancelled: { status: ["cancelled_by_merchandiser", "cancelled_by_accounts"] },
};

export default function MerchandiserDashboard() {
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<RequestSort>("newest");
  const [formOpen, setFormOpen] = useState(false);
  const debouncedSearch = useDebouncedValue(search.trim());
  const { data: activity = [] } = useMyActivity();

  // /merchandiser/new redirects here with ?new=1 — auto-expand the form so
  // old bookmarks still land on an open request form.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("new") === "1") {
      setFormOpen(true);
    }
  }, []);

  const { data, isLoading, isFetching } = useRequestsPaginated(page, PAGE_SIZE, {
    ...TAB_PARAMS[activeTab],
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(sort !== "newest" ? { sort } : {}),
  });
  const requests = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Pre-fetch counts for stat cards (page 1 only, just to get totals)
  const { data: allData }       = useRequestsPaginated(1, 1, {});
  const { data: pendingData }   = useRequestsPaginated(1, 1, { status: "pending_payment" });
  const { data: processedData } = useRequestsPaginated(1, 1, { status: "payment_processed" });
  const { data: cancelledData } = useRequestsPaginated(1, 1, { status: ["cancelled_by_merchandiser", "cancelled_by_accounts"] });

  function changeTab(tab: string) {
    setActiveTab(tab);
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

  const stripItems = activity.slice(0, 5);

  return (
    <RoleGuard allowedRoles={["merchandiser", "super_admin"]}>
      <TopNav title="My Requests" subtitle="Track and manage your Supplier Advance Payment Requests" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">

        {/* New Request — the Supplier Advance Payment Request form lives in
            the queue as a collapsible section (Aug 2026 batch, item 2.2). */}
        <Card className="overflow-hidden">
          <button
            type="button"
            onClick={() => setFormOpen((open) => !open)}
            aria-expanded={formOpen}
            className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-muted/40 transition-colors"
          >
            <span className="flex items-center gap-2 font-semibold text-foreground text-sm">
              <Plus className="h-4 w-4" />
              New Supplier Advance Payment Request
            </span>
            <ChevronDown
              className={`h-4 w-4 text-muted-foreground transition-transform ${formOpen ? "rotate-180" : ""}`}
            />
          </button>
          {formOpen && (
            <div className="border-t border-border p-4 md:p-6 bg-muted/20">
              <NewRequestForm
                onSuccess={() => setFormOpen(false)}
                onCancel={() => setFormOpen(false)}
              />
            </div>
          )}
        </Card>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Requests"   value={allData?.total ?? "—"}       icon={ClipboardList} />
          <StatCard label="Pending Payment"  value={pendingData?.total ?? "—"}   icon={Clock}         subtext="Awaiting accounts" />
          <StatCard label="Processed"        value={processedData?.total ?? "—"} icon={CheckCircle} />
          <StatCard label="Cancelled"        value={cancelledData?.total ?? "—"} icon={XCircle} />
        </div>

        {activity.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Bell className="h-4 w-4" />
                Recent Updates
              </h2>
              {activity.length > 5 && (
                <Link
                  href="/merchandiser/activity"
                  className="text-xs text-primary flex items-center gap-1 hover:underline"
                >
                  View all {activity.length} updates <ArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
            <div className="space-y-1.5">
              {stripItems.map((item) => (
                <Link href={`/merchandiser/${item.request_id}`} key={item.id}>
                  <div
                    className={`flex items-start justify-between gap-3 px-4 py-3 border-l-4 ${STATUS_BORDER[item.new_status]} bg-muted/30 rounded-r-lg hover:bg-muted/50 transition-colors`}
                  >
                    <div className="flex-1 min-w-0 space-y-1">
                      <p className="text-sm text-foreground flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono text-xs font-semibold bg-muted px-1.5 py-0.5 rounded shrink-0">
                          {item.request_number}
                        </span>
                        <span className="font-medium truncate">{item.supplier_name}</span>
                      </p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-muted-foreground">Status updated to</span>
                        <StatusBadge status={item.new_status} showFull />
                      </div>
                      {item.remarks && (
                        <p className="text-xs text-muted-foreground italic line-clamp-1">
                          &ldquo;{item.remarks}&rdquo;
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                      {timeAgo(item.changed_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-foreground">Request History</h2>
          <Button onClick={() => setFormOpen(true)} className="w-full sm:w-auto gap-2">
            <Plus className="h-4 w-4" /> New Request
          </Button>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <SearchInput
            value={search}
            onChange={changeSearch}
            placeholder="Search by invoice #, request #, supplier or customer…"
            className="sm:max-w-md flex-1"
          />
          <SortSelect value={sort} onChange={changeSort} className="sm:w-52" />
        </div>

        <Tabs value={activeTab} onValueChange={changeTab}>
          <TabsList className="w-full">
            <TabsTrigger value="all">All {allData ? `(${allData.total})` : ""}</TabsTrigger>
            <TabsTrigger value="pending">Pending {pendingData ? `(${pendingData.total})` : ""}</TabsTrigger>
            <TabsTrigger value="hold">On Hold</TabsTrigger>
            <TabsTrigger value="processed">Processed {processedData ? `(${processedData.total})` : ""}</TabsTrigger>
            <TabsTrigger value="cancelled">Cancelled {cancelledData ? `(${cancelledData.total})` : ""}</TabsTrigger>
          </TabsList>

          {(["all", "pending", "hold", "processed", "cancelled"] as const).map((tab) => (
            <TabsContent key={tab} value={tab}>
              {isLoading ? (
                <Card className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Request #</TableHead><TableHead>Supplier</TableHead>
                        <TableHead>Customer</TableHead><TableHead>Vertical</TableHead>
                        <TableHead>Deposit</TableHead><TableHead>Status</TableHead>
                        <TableHead>Date</TableHead><TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody><TableSkeleton rows={5} cols={8} /></TableBody>
                  </Table>
                </Card>
              ) : requests.length === 0 ? (
                debouncedSearch ? (
                  <RequestsTable requests={[]} basePath="/merchandiser" emptyMessage={`No requests match "${debouncedSearch}".`} />
                ) : tab === "all" ? (
                  <Card className="p-0">
                    <div className="flex flex-col items-center justify-center py-16 text-center px-4">
                      <div className="bg-muted rounded-full p-4 mb-4">
                        <ClipboardList className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <p className="font-semibold text-foreground text-base">No requests yet</p>
                      <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                        Use the New Request section above to raise your first
                        Supplier Advance Payment Request.
                      </p>
                    </div>
                  </Card>
                ) : (
                  <RequestsTable requests={[]} basePath="/merchandiser" emptyMessage={`No ${tab} requests.`} />
                )
              ) : (
                <div className={isFetching ? "opacity-70 transition-opacity" : ""}>
                  <RequestsTable requests={requests} basePath="/merchandiser" />
                  <Pagination
                    page={page}
                    totalPages={totalPages}
                    total={total}
                    pageSize={PAGE_SIZE}
                    onChange={setPage}
                  />
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </main>
    </RoleGuard>
  );
}

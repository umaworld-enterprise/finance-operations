"use client";

import { useState, useMemo, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient, useQuery, keepPreviousData } from "@tanstack/react-query";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { HelpTooltip } from "@/components/ui/HelpTooltip";
import { Pagination } from "@/components/ui/Pagination";
import dynamic from "next/dynamic";

// Recharts is ~65KB gzipped. Lazy-load so it's only downloaded when the
// Overview tab renders charts, not on initial page load.
const OverdueChart       = dynamic(() => import("@/components/charts/OverdueChart").then(m => ({ default: m.OverdueChart })), { ssr: false });
const CostOfFundChart    = dynamic(() => import("@/components/charts/CostOfFundChart").then(m => ({ default: m.CostOfFundChart })), { ssr: false });
const MonthlyTrendChart  = dynamic(() => import("@/components/charts/MonthlyTrendChart").then(m => ({ default: m.MonthlyTrendChart })), { ssr: false });
import { useAnalyticsSummary, useAnalyticsSnapshots, useWeeklyDeposits } from "@/hooks/useAnalytics";
import { useRequests } from "@/hooks/useRequests";
import { useVerticals, useCustomers, useUsers } from "@/hooks/useMasters";
import { currencyDisplayLabel, formatCurrency, formatDate, cn } from "@/lib/utils";
import { analyticsService, type AnalyticsFilters } from "@/services/analyticsService";
import type { MonthlyTrendPoint } from "@/components/charts/MonthlyTrendChart";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import Link from "next/link";
import {
  TrendingUp, AlertTriangle, DollarSign, Clock, RefreshCw,
  ChevronDown, ChevronUp, Check, AlertCircle, X, Filter,
  Package, Truck, Activity, Lock, ExternalLink,
} from "lucide-react";
import { toast } from "sonner";

// ── Small helpers ─────────────────────────────────────────────────────────────

function fmtCurrency(val: number, cur: string) {
  if (!val) return "—";
  const sym: Record<string, string> = { USD: "$", CNY: "¥", EUR: "€" };
  return (sym[cur] ?? "") + val.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function DefaultStatusPill({ status }: { status: string | null | undefined }) {
  if (status === "critical") return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-foreground text-background">
      <X className="h-3 w-3" /> Critical
    </span>
  );
  if (status === "delayed") return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium border border-dashed border-foreground/40 bg-background text-foreground">
      <AlertCircle className="h-3 w-3" /> Delayed
    </span>
  );
  if (status === "on_time") return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-secondary text-secondary-foreground border border-border">
      <Check className="h-3 w-3" /> On time
    </span>
  );
  return (
    <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium bg-muted text-muted-foreground">
      {status ?? "pending"}
    </span>
  );
}

function EmptyTable({ cols }: { cols: number }) {
  return (
    <TableRow>
      <TableCell colSpan={cols} className="text-center py-12 text-sm text-muted-foreground">
        No data yet. Run <strong>Recalculate</strong> after the first Sheets sync completes.
      </TableCell>
    </TableRow>
  );
}

// ── Data hooks ────────────────────────────────────────────────────────────────

const ANALYTICS_STALE = 5 * 60_000;
const ANALYTICS_GC    = 30 * 60_000;

function useAnalyticsPermissions() {
  return useQuery<Record<string, boolean>>({
    queryKey: ["analytics-permissions"],
    queryFn: async () => { const r = await api.get("/analytics/my-permissions"); return r.data; },
    staleTime: 60_000,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function buildQs(params: Record<string, string | number | undefined | null>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && String(v) !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

// Delay-bucket dropdown options shared across the 4 cross-filter tabs.
const DELAY_BUCKET_OPTIONS = [
  { label: "G-15 Days",    etd_min: 1,   etd_max: 15  },
  { label: "15-30 Days",   etd_min: 15,  etd_max: 30  },
  { label: "30-45 Days",   etd_min: 30,  etd_max: 45  },
  { label: "45-60 Days",   etd_min: 45,  etd_max: 60  },
  { label: "60-75 Days",   etd_min: 60,  etd_max: 75  },
  { label: "75-90 Days",   etd_min: 75,  etd_max: 90  },
  { label: "90-105 Days",  etd_min: 90,  etd_max: 105 },
  { label: "105-120 Days", etd_min: 105, etd_max: 120 },
  { label: "120-135 Days", etd_min: 120, etd_max: 135 },
  { label: "135-150 Days", etd_min: 135, etd_max: 150 },
  { label: "150+ Days",    etd_min: 150, etd_max: null },
];

// Encode a bucket option as a select value; parse back on use.
function encodeBucket(opt: typeof DELAY_BUCKET_OPTIONS[0]) {
  return `${opt.etd_min}_${opt.etd_max ?? ""}`;
}
function decodeBucket(val: string): { etd_min?: number; etd_max?: number } {
  if (!val) return {};
  const [minStr, maxStr] = val.split("_");
  return {
    etd_min: minStr ? Number(minStr) : undefined,
    etd_max: maxStr ? Number(maxStr) : undefined,
  };
}

interface TabFilters {
  dateFrom?: string;
  dateTo?: string;
  staffId?: string;
  verticalId?: string;
  customerId?: string;
  etdMin?: number;
  etdMax?: number;
}

function useOverdueByCurrency(enabled: boolean, dateFrom?: string, dateTo?: string) {
  return useQuery<{ currency: string; cases: number; overdue_amount: number; notional_gain: number }[]>({
    queryKey: ["analytics-overdue-currency", dateFrom, dateTo],
    queryFn: async () => { const r = await api.get(`/analytics/overdue-by-currency${buildQs({ date_from: dateFrom, date_to: dateTo })}`); return r.data; },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useShipmentKpis(enabled: boolean, dateFrom?: string, dateTo?: string) {
  return useQuery<{ total_overdue: number; etd_grace_pending: number; total_shipped: number; yet_to_ship: number; total_active: number }>({
    queryKey: ["analytics-shipment-kpis", dateFrom, dateTo],
    queryFn: async () => { const r = await api.get(`/analytics/shipment-kpis${buildQs({ date_from: dateFrom, date_to: dateTo })}`); return r.data; },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useDelayBuckets(enabled: boolean, filters: TabFilters) {
  return useQuery<any[]>({
    queryKey: ["analytics-delay-buckets", filters],
    queryFn: async () => {
      const r = await api.get(`/analytics/delay-buckets${buildQs({
        date_from: filters.dateFrom, date_to: filters.dateTo,
        staff_id: filters.staffId, vertical_id: filters.verticalId, customer_id: filters.customerId,
      })}`);
      return r.data;
    },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useByMerchandiser(enabled: boolean, filters: TabFilters) {
  return useQuery<any[]>({
    queryKey: ["analytics-by-merchandiser", filters],
    queryFn: async () => {
      const r = await api.get(`/analytics/by-merchandiser${buildQs({
        date_from: filters.dateFrom, date_to: filters.dateTo,
        vertical_id: filters.verticalId, customer_id: filters.customerId,
        etd_min: filters.etdMin, etd_max: filters.etdMax,
      })}`);
      return r.data;
    },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useByVertical(enabled: boolean, filters: TabFilters) {
  return useQuery<any[]>({
    queryKey: ["analytics-by-vertical", filters],
    queryFn: async () => {
      const r = await api.get(`/analytics/by-vertical${buildQs({
        date_from: filters.dateFrom, date_to: filters.dateTo,
        staff_id: filters.staffId, customer_id: filters.customerId,
        etd_min: filters.etdMin, etd_max: filters.etdMax,
      })}`);
      return r.data;
    },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useByCustomer(enabled: boolean, filters: TabFilters) {
  return useQuery<any[]>({
    queryKey: ["analytics-by-customer", filters],
    queryFn: async () => {
      const r = await api.get(`/analytics/by-customer${buildQs({
        date_from: filters.dateFrom, date_to: filters.dateTo,
        staff_id: filters.staffId, vertical_id: filters.verticalId,
        etd_min: filters.etdMin, etd_max: filters.etdMax,
      })}`);
      return r.data;
    },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

interface OutstandingRow {
  group: string;
  tranche_count: number;
  request_count: number;
  outstanding: Record<string, number>;
}

function useOutstandingTracker(enabled: boolean, groupBy: string, dateFrom?: string, dateTo?: string) {
  return useQuery<OutstandingRow[]>({
    queryKey: ["analytics-outstanding", groupBy, dateFrom, dateTo],
    queryFn: async () => {
      const r = await api.get(`/analytics/outstanding${buildQs({ group_by: groupBy, date_from: dateFrom, date_to: dateTo })}`);
      return r.data;
    },
    enabled,
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

function useMonthlyTrends(year: number) {
  return useQuery<MonthlyTrendPoint[]>({
    queryKey: ["analytics-monthly-trends", year],
    queryFn: async () => { const r = await api.get(`/analytics/monthly-trends?year=${year}`); return r.data; },
    staleTime: ANALYTICS_STALE,
    gcTime: ANALYTICS_GC,
    placeholderData: keepPreviousData,
  });
}

// ── Tab definitions ───────────────────────────────────────────────────────────

const ALL_TABS = [
  { key: "overview",        label: "Overview",        permKey: null },
  { key: "overdue_kpis",    label: "Overdue KPIs",    permKey: "overdue_kpis" },
  { key: "shipment_kpis",   label: "Shipment Report", permKey: "shipment_kpis" },
  { key: "delay_buckets",   label: "Delay Buckets",   permKey: "delay_buckets" },
  { key: "by_merchandiser", label: "By Merchandiser", permKey: "by_merchandiser" },
  { key: "by_vertical",     label: "By Vertical",     permKey: "by_vertical" },
  { key: "by_customer",     label: "By Customer",     permKey: "by_customer" },
  { key: "outstanding_tracker", label: "Outstanding", permKey: "outstanding_tracker" },
  // Weekly Deposit Tracker (Aug 2026, item 4.1) — same permission section as
  // Outstanding: identical data domain, different cut.
  { key: "weekly_tracker",  label: "Weekly Tracker",  permKey: "outstanding_tracker" },
] as const;

type TabKey = typeof ALL_TABS[number]["key"];

// ── Sub-tab components ────────────────────────────────────────────────────────

function OverdueKpisTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const { data = [], isLoading } = useOverdueByCurrency(true, dateFrom, dateTo);
  const currencies = ["USD", "CNY", "EUR"];
  const byC = (cur: string) => data.find((d) => d.currency === cur);

  if (isLoading) {
    return <div className="grid grid-cols-2 md:grid-cols-3 gap-4">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">Deposit Overdue (excl. Grace 10 days)</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {currencies.map((cur) => {
            const d = byC(cur);
            return (
              <Link
                key={cur}
                href={`/analytics/drill?section=overdue_kpis&currency=${cur}&metric=overdue`}
                className="group"
              >
                <Card className="relative overflow-hidden border-l-4 border-l-foreground transition-shadow group-hover:shadow-md cursor-pointer">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Deposit Overdue ({cur})</p>
                      <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors shrink-0 mt-0.5" />
                    </div>
                    <p className="text-2xl font-bold text-foreground">{d ? fmtCurrency(d.overdue_amount, cur) : "—"}</p>
                    {d ? <p className="text-xs text-muted-foreground mt-1">{d.cases} overdue case{d.cases !== 1 ? "s" : ""} · click to drill down</p>
                       : <p className="text-xs text-muted-foreground mt-1">Pending first sync</p>}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
      <div>
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">Notional Gain / Loss</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {currencies.map((cur) => {
            const d = byC(cur);
            return (
              <Link
                key={cur}
                href={`/analytics/drill?section=overdue_kpis&currency=${cur}&metric=notional`}
                className="group"
              >
                <Card className="relative overflow-hidden border-l-4 border-l-primary transition-shadow group-hover:shadow-md cursor-pointer">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Notional Gain ({cur})</p>
                      <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors shrink-0 mt-0.5" />
                    </div>
                    <p className="text-2xl font-bold text-foreground">{d ? fmtCurrency(d.notional_gain, cur) : "—"}</p>
                    {d ? <p className="text-xs text-muted-foreground mt-1">click to see contributing records</p>
                       : <p className="text-xs text-muted-foreground mt-1">Pending first sync</p>}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ShipmentKpisTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const { data, isLoading, isError, error } = useShipmentKpis(true, dateFrom, dateTo);

  const cards = [
    { label: "Total Overdue Shipments", sublabel: "Beyond ETD+10 day grace", value: data?.total_overdue, danger: true,  drillFilter: "overdue"    },
    { label: "ETD −10 Grace Days",       sublabel: "Approaching deadline",      value: data?.etd_grace_pending, danger: true,  drillFilter: "etd_grace"  },
    { label: "Total Shipped",             sublabel: "Payment processed",          value: data?.total_shipped, danger: false, drillFilter: "shipped"    },
    { label: "Yet to Ship",               sublabel: "Still pending",              value: data?.yet_to_ship, danger: false, drillFilter: "yet_to_ship"},
    { label: "Total Active Entries",      sublabel: "All non-deleted requests",   value: data?.total_active, danger: false, drillFilter: "active"     },
  ];

  if (isLoading) {
    return <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>;
  }

  if (isError) {
    console.error("ShipmentKPIs error:", error);
    return (
      <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Could not load shipment KPIs. Please try refreshing or contact your administrator.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {cards.map((c) => (
        <Link
          key={c.label}
          href={`/analytics/drill?section=shipment_kpis&filter=${c.drillFilter}`}
          className="group"
        >
          <Card className={cn("relative overflow-hidden border-l-4 transition-shadow group-hover:shadow-md cursor-pointer", c.danger ? "border-l-foreground" : "border-l-primary")}>
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-medium text-muted-foreground mb-1">{c.label}</p>
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors shrink-0 mt-0.5" />
              </div>
              <p className="text-3xl font-bold text-foreground">{c.value ?? "—"}</p>
              <p className="text-xs text-muted-foreground mt-1">{c.sublabel}</p>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}

// Reusable inline filter bar for cross-tab filters.
function TabFilterBar({
  showStaff, showVertical, showCustomer, showBucket,
  staffId, verticalId, customerId, bucketVal,
  onStaff, onVertical, onCustomer, onBucket, onClear,
}: {
  showStaff?: boolean; showVertical?: boolean; showCustomer?: boolean; showBucket?: boolean;
  staffId: string; verticalId: string; customerId: string; bucketVal: string;
  onStaff: (v: string) => void; onVertical: (v: string) => void;
  onCustomer: (v: string) => void; onBucket: (v: string) => void;
  onClear: () => void;
}) {
  const { data: verticals = [] } = useVerticals();
  const { data: customers = [] } = useCustomers();
  const { data: users = [] } = useUsers();
  const hasFilter = staffId || verticalId || customerId || bucketVal;
  return (
    <div className="flex flex-wrap items-end gap-2 mb-3">
      {showStaff && (
        <div className="min-w-[140px]">
          <Label className="text-xs mb-1 block">Merchandiser</Label>
          <Select value={staffId} onChange={(e) => onStaff(e.target.value)} className="text-xs">
            <option value="">All merchandisers</option>
            {users.map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        </div>
      )}
      {showVertical && (
        <div className="min-w-[130px]">
          <Label className="text-xs mb-1 block">Vertical</Label>
          <Select value={verticalId} onChange={(e) => onVertical(e.target.value)} className="text-xs">
            <option value="">All verticals</option>
            {verticals.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>
        </div>
      )}
      {showCustomer && (
        <div className="min-w-[130px]">
          <Label className="text-xs mb-1 block">Customer</Label>
          <Select value={customerId} onChange={(e) => onCustomer(e.target.value)} className="text-xs">
            <option value="">All customers</option>
            {customers.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
      )}
      {showBucket && (
        <div className="min-w-[150px]">
          <Label className="text-xs mb-1 block">Delay Bucket</Label>
          <Select value={bucketVal} onChange={(e) => onBucket(e.target.value)} className="text-xs">
            <option value="">All delay ranges</option>
            {DELAY_BUCKET_OPTIONS.map((o) => (
              <option key={encodeBucket(o)} value={encodeBucket(o)}>{o.label}</option>
            ))}
          </Select>
        </div>
      )}
      {hasFilter && (
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors pb-0.5"
        >
          <X className="h-3 w-3" /> Clear
        </button>
      )}
    </div>
  );
}

function DelayBucketsTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const [staffId, setStaffId] = useState("");
  const [verticalId, setVerticalId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const filters: TabFilters = { dateFrom, dateTo, staffId: staffId || undefined, verticalId: verticalId || undefined, customerId: customerId || undefined };
  const { data = [], isLoading } = useDelayBuckets(true, filters);
  return (
    <div className="space-y-3">
      <TabFilterBar
        showStaff showVertical showCustomer
        staffId={staffId} verticalId={verticalId} customerId={customerId} bucketVal=""
        onStaff={setStaffId} onVertical={setVerticalId} onCustomer={setCustomerId} onBucket={() => {}}
        onClear={() => { setStaffId(""); setVerticalId(""); setCustomerId(""); }}
      />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-32">Delay Range</TableHead>
                <TableHead className="text-right">Cases</TableHead>
                <TableHead className="text-right">Overdue USD</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue CNY</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue EUR</TableHead>
                <TableHead className="text-right">% of Delayed</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Notional USD</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Notional CNY</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Notional EUR</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton rows={11} cols={9} />
                : data.length === 0 ? <EmptyTable cols={9} />
                : data.map((row: any) => {
                  const minPart = row.bucket_min !== null && row.bucket_min !== undefined ? `&min=${row.bucket_min}` : "";
                  const xf = (staffId ? `&staff_id=${staffId}` : "") + (verticalId ? `&vertical_id=${verticalId}` : "") + (customerId ? `&customer_id=${customerId}` : "");
                  const drillUrl = `/analytics/drill?section=delay_buckets&label=${encodeURIComponent(row.delay_range)}${minPart}&max=${row.bucket_max}${xf}`;
                  return (
                  <TableRow key={row.delay_range} className="hover:bg-muted/40 cursor-pointer">
                    <TableCell className="font-medium text-sm">
                      <Link href={drillUrl} className="flex items-center gap-1.5 group/link hover:text-foreground transition-colors">
                        {row.delay_range}
                        <ExternalLink className="h-3 w-3 opacity-0 group-hover/link:opacity-60 transition-opacity shrink-0" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.cases}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtCurrency(row.overdue_usd, "USD")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_cny, "CNY")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_eur, "EUR")}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">{row.pct_of_delayed_cases}%</TableCell>
                    <TableCell className="text-right tabular-nums hidden lg:table-cell text-muted-foreground">{fmtCurrency(row.notional_usd, "USD")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden lg:table-cell text-muted-foreground">{fmtCurrency(row.notional_cny, "CNY")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden lg:table-cell text-muted-foreground">{fmtCurrency(row.notional_eur, "EUR")}</TableCell>
                  </TableRow>
                ); })}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

function ByMerchandiserTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const [verticalId, setVerticalId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [bucketVal, setBucketVal] = useState("");
  const { etd_min: etdMin, etd_max: etdMax } = decodeBucket(bucketVal);
  const filters: TabFilters = { dateFrom, dateTo, verticalId: verticalId || undefined, customerId: customerId || undefined, etdMin, etdMax };
  const { data = [], isLoading } = useByMerchandiser(true, filters);
  return (
    <div className="space-y-3">
      <TabFilterBar
        showVertical showCustomer showBucket
        staffId="" verticalId={verticalId} customerId={customerId} bucketVal={bucketVal}
        onStaff={() => {}} onVertical={setVerticalId} onCustomer={setCustomerId} onBucket={setBucketVal}
        onClear={() => { setVerticalId(""); setCustomerId(""); setBucketVal(""); }}
      />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Merchandiser</TableHead>
                <TableHead className="text-right">Overdue Cases</TableHead>
                <TableHead className="text-right">Overdue USD</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue CNY</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue EUR</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Avg Delay</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Notional Gain</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton rows={8} cols={8} />
                : data.length === 0 ? <EmptyTable cols={8} />
                : data.map((row: any) => (
                  <TableRow key={row.merchandiser} className="hover:bg-muted/40 cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/analytics/drill?section=by_merchandiser&name=${encodeURIComponent(row.merchandiser)}${verticalId ? `&vertical_id=${verticalId}` : ""}${customerId ? `&customer_id=${customerId}` : ""}${etdMin !== undefined ? `&etd_min=${etdMin}` : ""}${etdMax !== undefined ? `&etd_max=${etdMax}` : ""}`} className="flex items-center gap-1.5 group/link hover:text-foreground transition-colors">
                        {row.merchandiser}
                        <ExternalLink className="h-3 w-3 opacity-0 group-hover/link:opacity-60 transition-opacity shrink-0" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.overdue_cases}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtCurrency(row.overdue_usd, "USD")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_cny, "CNY")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_eur, "EUR")}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.contribution_pct}%</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{row.avg_delay_days}d</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{fmtCurrency(row.notional_gain, "USD")}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

function ByVerticalTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const [staffId, setStaffId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [bucketVal, setBucketVal] = useState("");
  const { etd_min: etdMin, etd_max: etdMax } = decodeBucket(bucketVal);
  const filters: TabFilters = { dateFrom, dateTo, staffId: staffId || undefined, customerId: customerId || undefined, etdMin, etdMax };
  const { data = [], isLoading } = useByVertical(true, filters);
  return (
    <div className="space-y-3">
      <TabFilterBar
        showStaff showCustomer showBucket
        staffId={staffId} verticalId="" customerId={customerId} bucketVal={bucketVal}
        onStaff={setStaffId} onVertical={() => {}} onCustomer={setCustomerId} onBucket={setBucketVal}
        onClear={() => { setStaffId(""); setCustomerId(""); setBucketVal(""); }}
      />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Overdue Cases</TableHead>
                <TableHead className="text-right">Overdue USD</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue CNY</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue EUR</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Avg Delay</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Notional Gain</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton rows={8} cols={8} />
                : data.length === 0 ? <EmptyTable cols={8} />
                : data.map((row: any) => (
                  <TableRow key={row.category} className="hover:bg-muted/40 cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/analytics/drill?section=by_vertical&name=${encodeURIComponent(row.category)}${staffId ? `&staff_id=${staffId}` : ""}${customerId ? `&customer_id=${customerId}` : ""}${etdMin !== undefined ? `&etd_min=${etdMin}` : ""}${etdMax !== undefined ? `&etd_max=${etdMax}` : ""}`} className="flex items-center gap-1.5 group/link hover:text-foreground transition-colors">
                        {row.category}
                        <ExternalLink className="h-3 w-3 opacity-0 group-hover/link:opacity-60 transition-opacity shrink-0" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.overdue_cases}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtCurrency(row.overdue_usd, "USD")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_cny, "CNY")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_eur, "EUR")}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.contribution_pct}%</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{row.avg_delay_days}d</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{fmtCurrency(row.notional_gain, "USD")}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

function ByCustomerTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const [staffId, setStaffId] = useState("");
  const [verticalId, setVerticalId] = useState("");
  const [bucketVal, setBucketVal] = useState("");
  const { etd_min: etdMin, etd_max: etdMax } = decodeBucket(bucketVal);
  const filters: TabFilters = { dateFrom, dateTo, staffId: staffId || undefined, verticalId: verticalId || undefined, etdMin, etdMax };
  const { data = [], isLoading } = useByCustomer(true, filters);
  return (
    <div className="space-y-3">
      <TabFilterBar
        showStaff showVertical showBucket
        staffId={staffId} verticalId={verticalId} customerId="" bucketVal={bucketVal}
        onStaff={setStaffId} onVertical={setVerticalId} onCustomer={() => {}} onBucket={setBucketVal}
        onClear={() => { setStaffId(""); setVerticalId(""); setBucketVal(""); }}
      />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Cases</TableHead>
                <TableHead className="text-right">Overdue USD</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue CNY</TableHead>
                <TableHead className="text-right hidden md:table-cell">Overdue EUR</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Avg Delay</TableHead>
                <TableHead className="text-right hidden lg:table-cell">Max Delay</TableHead>
                <TableHead className="text-right hidden lg:table-cell">ETD Pending</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton rows={8} cols={9} />
                : data.length === 0 ? <EmptyTable cols={9} />
                : data.map((row: any) => (
                  <TableRow key={row.customer} className="hover:bg-muted/40 cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/analytics/drill?section=by_customer&name=${encodeURIComponent(row.customer)}${staffId ? `&staff_id=${staffId}` : ""}${verticalId ? `&vertical_id=${verticalId}` : ""}${etdMin !== undefined ? `&etd_min=${etdMin}` : ""}${etdMax !== undefined ? `&etd_max=${etdMax}` : ""}`} className="flex items-center gap-1.5 group/link hover:text-foreground transition-colors">
                        {row.customer}
                        <ExternalLink className="h-3 w-3 opacity-0 group-hover/link:opacity-60 transition-opacity shrink-0" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.overdue_cases}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtCurrency(row.overdue_usd, "USD")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_cny, "CNY")}</TableCell>
                    <TableCell className="text-right tabular-nums hidden md:table-cell">{fmtCurrency(row.overdue_eur, "EUR")}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.contribution_pct}%</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{row.avg_delay_days}d</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{row.max_delay_days}d</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground hidden lg:table-cell">{row.etd_pending}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

// ── Outstanding Deposit Tracker ───────────────────────────────────────────────
// A payment requested by a merchandiser stays outstanding until it is paid —
// calculated at tranche level, so only unpaid requested tranche value counts.

const OUTSTANDING_GROUPS = [
  { key: "week",         label: "Weekly (request date)" },
  { key: "merchandiser", label: "Merchandiser" },
  { key: "customer",     label: "Customer" },
  { key: "vertical",     label: "Vertical" },
] as const;

function OutstandingTrackerTab({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) {
  const [groupBy, setGroupBy] = useState<string>("week");
  const { data = [], isLoading } = useOutstandingTracker(true, groupBy, dateFrom, dateTo);

  // Currency columns are driven by the data — USD/CNY/EUR first, then any
  // other currency present, so nothing is artificially hidden.
  const currencies = useMemo(() => {
    const preferred = ["USD", "CNY", "EUR"];
    const present = new Set<string>();
    data.forEach((row) => Object.keys(row.outstanding).forEach((c) => present.add(c)));
    return [
      ...preferred.filter((c) => present.has(c)),
      ...[...present].filter((c) => !preferred.includes(c)).sort(),
    ];
  }, [data]);
  const cols = 3 + Math.max(currencies.length, 1);

  const groupHeading = OUTSTANDING_GROUPS.find((g) => g.key === groupBy)?.label ?? "Group";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Group by:</span>
        <select
          value={groupBy}
          onChange={(e) => setGroupBy(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {OUTSTANDING_GROUPS.map((g) => (
            <option key={g.key} value={g.key}>{g.label}</option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Unpaid requested tranche value only — paid tranches are excluded, so partial
          payments are reflected. Weekly ranges run Monday–Sunday on the request-created date.
        </p>
      </div>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{groupHeading}</TableHead>
                <TableHead className="text-right">Requests</TableHead>
                <TableHead className="text-right">Unpaid Tranches</TableHead>
                {currencies.length === 0 ? (
                  <TableHead className="text-right">Outstanding</TableHead>
                ) : (
                  currencies.map((c) => (
                    <TableHead key={c} className="text-right">Outstanding {currencyDisplayLabel(c)}</TableHead>
                  ))
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton rows={8} cols={cols} />
                : data.length === 0 ? <EmptyTable cols={cols} />
                : data.map((row) => (
                  <TableRow key={row.group}>
                    <TableCell className="font-medium text-sm whitespace-nowrap">{row.group}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.request_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.tranche_count}</TableCell>
                    {currencies.length === 0 ? (
                      <TableCell className="text-right tabular-nums">—</TableCell>
                    ) : (
                      currencies.map((c) => (
                        <TableCell key={c} className="text-right tabular-nums">
                          {row.outstanding[c] != null ? fmtCurrency(row.outstanding[c], c) : "—"}
                        </TableCell>
                      ))
                    )}
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

function WeeklyTrackerTab() {
  const { data: groups = [], isLoading } = useWeeklyDeposits();
  const { user } = useAuth();
  // Request numbers link to the viewer's own detail page (19 Aug 2026,
  // app-wide hyperlinks).
  const requestHref = (id: string) =>
    user?.role === "merchandiser"
      ? `/merchandiser/${id}`
      : user?.role === "head_of_merchandiser"
        ? `/hom/${id}`
        : `/accounts/${id}`;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Requested, unpaid deposits sorted by ETD, bucketed into the
        ETD&apos;s Monday–Sunday week. Requests without an ETD collect at the bottom.
      </p>
      {isLoading ? (
        <Card className="overflow-hidden">
          <Table>
            <TableBody><TableSkeleton rows={8} cols={7} /></TableBody>
          </Table>
        </Card>
      ) : groups.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          No unpaid deposits — the tracker is clear.
        </Card>
      ) : (
        groups.map((g) => (
          <Card key={g.week_start ?? "no-etd"} className="overflow-hidden">
            <div className="px-5 py-3 border-b border-border flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">
                {g.week_start ? `ETD week ${g.week}` : g.week}
              </span>
              <span className="text-xs text-muted-foreground">
                {Object.entries(g.outstanding)
                  .map(([cur, amt]) => fmtCurrency(amt, cur))
                  .join(" · ")}
              </span>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Request #</TableHead>
                    <TableHead>Invoice #</TableHead>
                    <TableHead>Supplier</TableHead>
                    <TableHead>Tranche</TableHead>
                    <TableHead className="text-right">Unpaid Amount</TableHead>
                    <TableHead>Tentative Payment</TableHead>
                    <TableHead>ETD</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {g.rows.map((row, i) => (
                    <TableRow key={`${row.request_id}-${row.tranche_label}-${i}`}>
                      <TableCell className="font-mono text-xs font-semibold whitespace-nowrap">
                        <Link
                          href={requestHref(row.request_id)}
                          className="hover:underline underline-offset-2"
                        >
                          {row.request_number}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {row.sunshine_invoice_number || "—"}
                      </TableCell>
                      <TableCell className="text-sm">{row.supplier_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {row.tranche_label}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-semibold">
                        {fmtCurrency(row.amount, row.currency)}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">
                        {row.tentative_payment_date ? formatDate(row.tentative_payment_date) : "—"}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">
                        {row.estimated_etd ? formatDate(row.estimated_etd) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}


// ── Overview tab (original analytics content) ─────────────────────────────────

const GLOSSARY = [
  { term: "Grace ETD", def: "The estimated shipment date plus a configurable grace period (default 7 days). Requests past this date are considered overdue." },
  { term: "ETD Overdue (days)", def: "How many days past the Grace ETD the shipment is. Zero means on time." },
  { term: "Pmt→Ship (days)", def: "Days between the payment being processed and the actual ship date. Lower is better." },
  { term: "Pmt→Request (days)", def: "Days between the advance payment request being submitted and the payment being processed." },
  { term: "Cost of Fund", def: "The financial cost of the shipment delay, calculated as deposit amount × annual rate × (delay days ÷ 365), where delay days run from the Grace ETD to the actual shipment date (or today while unshipped). Zero if shipped within grace. The rate is configurable by admins." },
  { term: "Default Status", def: "A risk classification: 'critical' = significantly overdue, 'delayed' = moderately overdue, 'on_time' = within grace period." },
];

const SNAPS_PAGE_SIZE = 25;

function OverviewTab({ filters, draftFilters, setDraft, applyFilters, clearFilters, hasFilters }: {
  filters: AnalyticsFilters;
  draftFilters: AnalyticsFilters;
  setDraft: (key: keyof AnalyticsFilters, value?: string) => void;
  applyFilters: () => void;
  clearFilters: () => void;
  hasFilters: boolean;
}) {
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [snapsPage, setSnapsPage] = useState(1);
  const currentYear = new Date().getFullYear();
  const [trendYear, setTrendYear] = useState(currentYear);
  const YEAR_OPTIONS = [currentYear, currentYear - 1, currentYear - 2];
  const { data: monthlyTrends = [], isLoading: trendsLoading } = useMonthlyTrends(trendYear);
  const { data: verticals = [] } = useVerticals();
  const { data: customers = [] } = useCustomers();
  const { data: users = [] } = useUsers();
  const { data: allRequests = [] } = useRequests();
  const { data: summary, isLoading: summaryLoading } = useAnalyticsSummary(filters);
  const { data: snapshots = [], isLoading: snapshotsLoading } = useAnalyticsSnapshots(filters);

  const requestMap = useMemo(() => {
    const m = new Map<string, typeof allRequests[0]>();
    allRequests.forEach((r) => m.set(r.id, r));
    return m;
  }, [allRequests]);

  const bucketBreakdown = useMemo(() => {
    const counts: Record<string, number> = { critical: 0, delayed: 0, on_time: 0, pending: 0 };
    snapshots.forEach((s) => { const key = s.default_status ?? "pending"; counts[key] = (counts[key] ?? 0) + 1; });
    return counts;
  }, [snapshots]);

  const customerBreakdown = useMemo(() => {
    const map = new Map<string, { name: string; count: number; overdueDays: number; costOfFund: number }>();
    snapshots.forEach((s) => {
      const req = requestMap.get(s.deposit_request_id);
      if (!req || !req.customer) return;
      const e = map.get(req.customer.id) ?? { name: req.customer.name, count: 0, overdueDays: 0, costOfFund: 0 };
      e.count += 1; e.overdueDays += s.etd_grace_overdue_days ?? 0; e.costOfFund += Number(s.cost_of_fund_amount ?? 0);
      map.set(req.customer.id, e);
    });
    return [...map.values()].sort((a, b) => b.overdueDays - a.overdueDays);
  }, [snapshots, requestMap]);

  const verticalBreakdown = useMemo(() => {
    const map = new Map<string, { name: string; count: number; overdueDays: number; costOfFund: number }>();
    snapshots.forEach((s) => {
      const req = requestMap.get(s.deposit_request_id);
      if (!req || !req.vertical) return;
      const e = map.get(req.vertical.id) ?? { name: req.vertical.name, count: 0, overdueDays: 0, costOfFund: 0 };
      e.count += 1; e.overdueDays += s.etd_grace_overdue_days ?? 0; e.costOfFund += Number(s.cost_of_fund_amount ?? 0);
      map.set(req.vertical.id, e);
    });
    return [...map.values()].sort((a, b) => b.overdueDays - a.overdueDays);
  }, [snapshots, requestMap]);

  const snapsTotalPages = Math.ceil(snapshots.length / SNAPS_PAGE_SIZE);
  const snapsSlice = snapshots.slice((snapsPage - 1) * SNAPS_PAGE_SIZE, snapsPage * SNAPS_PAGE_SIZE);

  useEffect(() => { setSnapsPage(1); }, [snapshots]);

  return (
    <div className="space-y-6">
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold text-foreground">Filters</span>
            {hasFilters && (
              <button onClick={clearFilters} className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                <X className="h-3 w-3" /> Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs mb-1 block">Vertical</Label>
              <Select value={draftFilters.vertical_id ?? ""} onChange={(e) => setDraft("vertical_id", e.target.value)} className="text-xs">
                <option value="">All verticals</option>
                {verticals.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </div>
            <div>
              <Label className="text-xs mb-1 block">Customer</Label>
              <Select value={draftFilters.customer_id ?? ""} onChange={(e) => setDraft("customer_id", e.target.value)} className="text-xs">
                <option value="">All customers</option>
                {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
            <div>
              <Label className="text-xs mb-1 block">Staff</Label>
              <Select value={draftFilters.staff_id ?? ""} onChange={(e) => setDraft("staff_id", e.target.value)} className="text-xs">
                <option value="">All staff</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </Select>
            </div>
          </div>
          <div className="flex justify-end mt-3">
            <Button size="sm" onClick={applyFilters} className="text-xs px-4">
              <Filter className="h-3.5 w-3.5 mr-1.5" />
              Filter
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Glossary */}
      <Card>
        <button type="button" onClick={() => setGlossaryOpen(!glossaryOpen)} className="w-full flex items-center justify-between p-4 text-left">
          <span className="font-semibold text-foreground text-sm">Metrics Glossary — What do these terms mean?</span>
          {glossaryOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
        {glossaryOpen && (
          <CardContent className="pt-0 space-y-3">
            {GLOSSARY.map(({ term, def }) => (
              <div key={term} className="flex flex-col sm:flex-row gap-1 sm:gap-3">
                <span className="font-medium text-foreground text-sm shrink-0 sm:w-40">{term}</span>
                <span className="text-sm text-muted-foreground">{def}</span>
              </div>
            ))}
          </CardContent>
        )}
      </Card>

      {/* KPI summary */}
      {summaryLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Requests" value={summary?.total_requests ?? 0} icon={TrendingUp} />
          <StatCard label="Overdue Shipments" value={summary?.overdue_shipments ?? 0} icon={AlertTriangle} subtext="ETD grace exceeded" />
          <StatCard label="Avg Payment-to-Ship" value={`${summary?.avg_payment_to_ship_days?.toFixed(1) ?? "—"} days`} icon={Clock} />
          <StatCard label="Total Cost of Fund" value={formatCurrency(summary?.total_cost_of_fund ?? 0, "USD")} icon={DollarSign} />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6">
          <h2 className="font-semibold text-foreground mb-4 text-sm">Overdue by ETD Grace (Days)</h2>
          <OverdueChart snapshots={snapshots} />
        </Card>
        <Card className="p-6">
          <h2 className="font-semibold text-foreground mb-4 text-sm">Cost of Fund Exposure (USD)</h2>
          <CostOfFundChart snapshots={snapshots} />
        </Card>
      </div>

      {/* Monthly MoM / YTD charts */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Month-on-Month &amp; YTD Trends</h2>
          <select
            value={trendYear}
            onChange={(e) => setTrendYear(Number(e.target.value))}
            className="text-xs border border-border rounded-md px-2 py-1 bg-background text-foreground"
          >
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-6">
            <h2 className="font-semibold text-foreground mb-1 text-sm">Overdue Days — MoM &amp; YTD</h2>
            <p className="text-xs text-muted-foreground mb-4">Monthly overdue-day total (bars) with YTD cumulative line</p>
            {trendsLoading ? (
              <div className="h-[220px] flex items-center justify-center"><Skeleton className="w-full h-full rounded-lg" /></div>
            ) : (
              <MonthlyTrendChart data={monthlyTrends} metric="overdue" />
            )}
          </Card>
          <Card className="p-6">
            <h2 className="font-semibold text-foreground mb-1 text-sm">Cost of Fund — MoM &amp; YTD</h2>
            <p className="text-xs text-muted-foreground mb-4">Monthly cost-of-fund (bars) with YTD cumulative line</p>
            {trendsLoading ? (
              <div className="h-[220px] flex items-center justify-center"><Skeleton className="w-full h-full rounded-lg" /></div>
            ) : (
              <MonthlyTrendChart data={monthlyTrends} metric="cost_of_fund" />
            )}
          </Card>
        </div>
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-foreground text-sm mb-4">By Delay Status</h2>
            <div className="space-y-3">
              {[
                { key: "critical", label: "Critical (>30d overdue)", className: "text-foreground font-semibold" },
                { key: "delayed",  label: "Delayed (1–30d overdue)", className: "text-foreground" },
                { key: "on_time",  label: "On Time",                 className: "text-muted-foreground" },
                { key: "pending",  label: "Pending / No ETD",        className: "text-muted-foreground" },
              ].map(({ key, label, className }) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{label}</span>
                  <span className={cn("tabular-nums", className)}>{bucketBreakdown[key] ?? 0}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-foreground text-sm mb-4">By Customer (overdue days)</h2>
            {customerBreakdown.length === 0 ? <p className="text-xs text-muted-foreground">No data</p> : (
              <div className="space-y-3">
                {customerBreakdown.slice(0, 6).map((c) => (
                  <div key={c.name} className="flex items-center justify-between text-sm gap-2">
                    <Link
                      href={`/analytics/drill?section=by_customer&name=${encodeURIComponent(c.name)}`}
                      className="text-muted-foreground truncate hover:text-foreground hover:underline underline-offset-2 transition-colors"
                    >
                      {c.name}
                    </Link>
                    <span className="shrink-0 font-semibold text-foreground tabular-nums">{c.overdueDays}d · {c.count} req</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-foreground text-sm mb-4">By Vertical (overdue days)</h2>
            {verticalBreakdown.length === 0 ? <p className="text-xs text-muted-foreground">No data</p> : (
              <div className="space-y-3">
                {verticalBreakdown.slice(0, 6).map((v) => (
                  <div key={v.name} className="flex items-center justify-between text-sm gap-2">
                    <Link
                      href={`/analytics/drill?section=by_vertical&name=${encodeURIComponent(v.name)}`}
                      className="text-muted-foreground truncate hover:text-foreground hover:underline underline-offset-2 transition-colors"
                    >
                      {v.name}
                    </Link>
                    <span className="shrink-0 font-semibold text-foreground tabular-nums">{v.overdueDays}d · {v.count} req</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Per-request table */}
      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border">
          <h2 className="font-semibold text-foreground text-sm">Per-Request Metrics</h2>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right"><span className="inline-flex items-center gap-1">Grace ETD <HelpTooltip content="Estimated shipment date + grace period (default 7 days)." /></span></TableHead>
              <TableHead className="text-right"><span className="inline-flex items-center gap-1">ETD Overdue <HelpTooltip content="Days past the Grace ETD. Zero means on time." /></span></TableHead>
              <TableHead className="text-right hidden md:table-cell"><span className="inline-flex items-center gap-1">Pmt→Ship <HelpTooltip content="Days from payment processed to ship date." /></span></TableHead>
              <TableHead className="text-right hidden md:table-cell"><span className="inline-flex items-center gap-1">Pmt→Request <HelpTooltip content="Days from request submission to payment processed." /></span></TableHead>
              <TableHead className="text-right"><span className="inline-flex items-center gap-1">Cost of Fund <HelpTooltip content="Estimated financial cost of holding the advance deposit." /></span></TableHead>
              <TableHead>Default</TableHead>
              <TableHead className="hidden lg:table-cell">Calculated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {snapshotsLoading ? (
              <TableSkeleton rows={8} cols={9} />
            ) : snapshots.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-12 text-muted-foreground text-sm">
                  No analytics data{hasFilters ? " for the selected filters" : ""}. Click <strong>Recalculate</strong> to generate.
                </TableCell>
              </TableRow>
            ) : (
              snapsSlice.map((s) => (
                <TableRow key={s.deposit_request_id}>
                  <TableCell>
                  <Link
                    href={`/accounts/${s.deposit_request_id}`}
                    className="font-mono text-xs font-semibold text-foreground hover:underline underline-offset-2"
                  >
                    {s.request_number ?? s.deposit_request_id.slice(0, 8)}
                  </Link>
                </TableCell>
                  <TableCell>{s.current_status ? <StatusBadge status={s.current_status} /> : "—"}</TableCell>
                  <TableCell className="text-right text-muted-foreground">{s.grace_etd ? formatDate(s.grace_etd) : "—"}</TableCell>
                  <TableCell className={cn("text-right font-medium", (s.etd_grace_overdue_days ?? 0) > 0 ? "text-foreground" : "text-muted-foreground")}>{s.etd_grace_overdue_days ?? 0}</TableCell>
                  <TableCell className="text-right text-muted-foreground hidden md:table-cell">{s.payment_to_ship_days ?? "—"}</TableCell>
                  <TableCell className="text-right text-muted-foreground hidden md:table-cell">{s.payment_to_request_days ?? "—"}</TableCell>
                  <TableCell className={cn("text-right font-medium", (s.cost_of_fund_amount ?? 0) > 0 ? "text-foreground" : "text-muted-foreground")}>{s.cost_of_fund_amount ? formatCurrency(Number(s.cost_of_fund_amount), s.currency ?? undefined) : "—"}</TableCell>
                  <TableCell><DefaultStatusPill status={s.default_status} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground hidden lg:table-cell">{formatDate(s.calculated_at)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
      <Pagination
        page={snapsPage}
        totalPages={snapsTotalPages}
        total={snapshots.length}
        pageSize={SNAPS_PAGE_SIZE}
        onChange={setSnapsPage}
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const [recalculating, setRecalculating] = useState(false);
  const initialTab = (searchParams.get("tab") as TabKey | null) ?? "overview";
  const [activeTab, setActiveTab] = useState<TabKey>(
    ALL_TABS.some((t) => t.key === initialTab) ? initialTab : "overview"
  );
  const [draftFilters, setDraftFilters] = useState<AnalyticsFilters>({});
  const [appliedFilters, setAppliedFilters] = useState<AnalyticsFilters>({});

  // Global date filter — applied across ALL tabs
  const [draftFrom, setDraftFrom] = useState("");
  const [draftTo, setDraftTo] = useState("");
  const [globalFrom, setGlobalFrom] = useState("");
  const [globalTo, setGlobalTo] = useState("");

  const { data: permissions, isLoading: permsLoading } = useAnalyticsPermissions();
  const isSuperAdmin = user?.role === "super_admin";
  const hasEntityFilters = Object.entries(appliedFilters).some(
    ([k, v]) => k !== "date_from" && k !== "date_to" && Boolean(v)
  );

  function setDraft(key: keyof AnalyticsFilters, value?: string) {
    setDraftFilters((f) => ({ ...f, [key]: value || undefined }));
  }

  function applyFilters() {
    setAppliedFilters({
      ...draftFilters,
      date_from: globalFrom || undefined,
      date_to: globalTo || undefined,
    });
  }

  function clearFilters() {
    setDraftFilters({});
    setAppliedFilters({ date_from: globalFrom || undefined, date_to: globalTo || undefined });
  }

  function applyGlobalDates() {
    setGlobalFrom(draftFrom);
    setGlobalTo(draftTo);
    setAppliedFilters((prev) => ({
      ...prev,
      date_from: draftFrom || undefined,
      date_to: draftTo || undefined,
    }));
  }

  function clearGlobalDates() {
    setDraftFrom("");
    setDraftTo("");
    setGlobalFrom("");
    setGlobalTo("");
    setAppliedFilters((prev) => ({ ...prev, date_from: undefined, date_to: undefined }));
  }

  const visibleTabs = ALL_TABS.filter((tab) => {
    if (!tab.permKey) return true;
    if (isSuperAdmin) return true;
    return permissions?.[tab.permKey] === true;
  });

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      await analyticsService.recalculate();
      await qc.invalidateQueries({ queryKey: ["analytics"] });
      await qc.invalidateQueries({ queryKey: ["analytics-overdue-currency"] });
      await qc.invalidateQueries({ queryKey: ["analytics-shipment-kpis"] });
      await qc.invalidateQueries({ queryKey: ["analytics-delay-buckets"] });
      await qc.invalidateQueries({ queryKey: ["analytics-by-merchandiser"] });
      await qc.invalidateQueries({ queryKey: ["analytics-by-vertical"] });
      await qc.invalidateQueries({ queryKey: ["analytics-by-customer"] });
      await qc.invalidateQueries({ queryKey: ["analytics-monthly-trends"] });
      toast.success("Analytics recalculated successfully.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Recalculation failed.");
    } finally {
      setRecalculating(false);
    }
  };

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"]}>
      <TopNav title="Analytics" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-4">

        {/* Global date filter + Recalculate on their own row — the picker
            used to sit inside the tab strip and covered the last tabs
            (Aug 2026 client bug report). */}
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground whitespace-nowrap">Period:</span>
            <input
              type="date"
              value={draftFrom}
              onChange={(e) => setDraftFrom(e.target.value)}
              className="h-8 rounded border border-border bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={draftTo}
              min={draftFrom || undefined}
              onChange={(e) => setDraftTo(e.target.value)}
              className="h-8 rounded border border-border bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <Button size="sm" onClick={applyGlobalDates} className="h-8 text-xs px-2.5">
              Apply
            </Button>
            {(globalFrom || globalTo) && (
              <Button size="sm" variant="ghost" onClick={clearGlobalDates} className="h-8 w-8 p-0 text-muted-foreground">
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>
          <Button onClick={handleRecalculate} disabled={recalculating} variant="outline" size="sm" className="h-8">
            <RefreshCw className={cn("h-4 w-4 mr-2", recalculating && "animate-spin")} />
            Recalculate
          </Button>
        </div>

        {/* Tab strip — full width, never overlapped */}
        {permsLoading ? (
          <div className="flex items-end gap-0.5 border-b border-border overflow-x-auto pb-0">
            {ALL_TABS.map((tab) => (
              <div
                key={tab.key}
                className="px-3 py-2 border-b-2 border-transparent opacity-40 animate-pulse"
              >
                <Skeleton className="h-4 w-20 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-end gap-0.5 border-b border-border overflow-x-auto">
            {visibleTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  "px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2",
                  activeTab === tab.key
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        {/* Tab content */}
        {activeTab === "overview" && (
          <OverviewTab
            filters={appliedFilters}
            draftFilters={draftFilters}
            setDraft={setDraft}
            applyFilters={applyFilters}
            clearFilters={clearFilters}
            hasFilters={hasEntityFilters}
          />
        )}
        {activeTab === "overdue_kpis" && <OverdueKpisTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "shipment_kpis" && <ShipmentKpisTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "delay_buckets" && <DelayBucketsTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "by_merchandiser" && <ByMerchandiserTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "by_vertical" && <ByVerticalTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "by_customer" && <ByCustomerTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "outstanding_tracker" && <OutstandingTrackerTab dateFrom={globalFrom} dateTo={globalTo} />}
        {activeTab === "weekly_tracker" && <WeeklyTrackerTab />}

        {/* Fallback: user landed on a tab they can't access */}
        {activeTab !== "overview" && !isSuperAdmin && !permsLoading && permissions &&
          ALL_TABS.find((t) => t.key === activeTab)?.permKey &&
          permissions[ALL_TABS.find((t) => t.key === activeTab)!.permKey!] === false && (
          <div className="flex flex-col items-center justify-center py-24 text-center gap-3 text-muted-foreground">
            <Lock className="h-8 w-8" />
            <p className="font-medium text-foreground">Access Restricted</p>
            <p className="text-sm">Contact your Super Admin to enable this analytics section.</p>
          </div>
        )}

      </main>
    </RoleGuard>
  );
}

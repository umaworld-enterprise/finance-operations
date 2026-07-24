"use client";

import { Suspense, useMemo, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Info, Hash, Users, BarChart3, Building2,
  ClipboardList, AlertTriangle, DollarSign, Clock,
} from "lucide-react";
import { Pagination } from "@/components/ui/Pagination";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { SearchInput } from "@/components/ui/SearchInput";
import { useRequests } from "@/hooks/useRequests";
import { useAnalyticsSnapshots } from "@/hooks/useAnalytics";
import { formatCurrency, formatDate, cn, requestMatchesSearch } from "@/lib/utils";
import type { DepositRequest, AnalyticsSnapshot, RequestStatus } from "@/types";

// ── Formatting ────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined, cur = "USD") {
  if (!val) return "—";
  const sym: Record<string, string> = { USD: "$", CNY: "¥", EUR: "€", GBP: "£" };
  return (sym[cur] ?? "") + val.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtPct(part: number, total: number) {
  if (!total) return "—";
  return ((part / total) * 100).toFixed(1) + "%";
}

// ── Drill-down config ─────────────────────────────────────────────────────────

type DrillMeta = {
  title: string;
  subtitle?: string;
  countLabel: string;
  formulaLines: string[];
  explanation: string;
  isMonetary: boolean;
  isEntity: boolean;
  sumColumn: "deposit_amount" | "cost_of_fund" | null;
  sumCurrency?: string;
  sectionIcon?: React.ReactNode;
};

function getDrillMeta(
  section: string,
  currency: string | null,
  metric: string | null,
  filter: string | null,
  name: string | null,
  bucketLabel: string | null,
): DrillMeta {
  // ── Overdue KPIs ────────────────────────────────────────────────────────────
  if (section === "overdue_kpis" && currency) {
    if (metric === "notional") {
      return {
        title: `Notional Gain / Loss — ${currency}`,
        countLabel: "overdue requests contributing",
        formulaLines: [
          `SUM(cost_of_fund_amount)`,
          `WHERE currency = ${currency}`,
          `  AND etd_grace_overdue_days > 0`,
          `  AND is_deleted = false`,
        ],
        explanation:
          `The notional gain/loss is the time-value cost of holding the advance deposit past the grace ETD. ` +
          `Each row's Cost of Fund is computed as: Deposit Amount × Annual Rate × (Days Overdue ÷ 365). ` +
          `Only ${currency} requests that are currently overdue are included.`,
        isMonetary: true,
        isEntity: false,
        sumColumn: "cost_of_fund",
        sumCurrency: currency,
      };
    }
    return {
      title: `Deposit Overdue — ${currency}`,
      countLabel: "overdue requests",
      formulaLines: [
        `SUM(deposit_amount)`,
        `WHERE currency = ${currency}`,
        `  AND etd_grace_overdue_days > 0`,
        `  AND is_deleted = false`,
      ],
      explanation:
        `Every active deposit request denominated in ${currency} whose Grace ETD has already passed is included. ` +
        `The KPI total on the dashboard is the sum of each row's Deposit Amount.`,
      isMonetary: true,
      isEntity: false,
      sumColumn: "deposit_amount",
      sumCurrency: currency,
    };
  }

  // ── Shipment KPIs ───────────────────────────────────────────────────────────
  if (section === "shipment_kpis") {
    const configs: Record<string, Omit<DrillMeta, "isEntity">> = {
      overdue: {
        title: "Total Overdue Shipments",
        countLabel: "overdue shipments",
        formulaLines: [`COUNT(*) WHERE etd_grace_overdue_days > 0 AND is_deleted = false`],
        explanation: `All active requests where the Grace ETD has passed and payment has not been processed.`,
        isMonetary: false,
        sumColumn: null,
      },
      etd_grace: {
        title: "ETD Grace Period (within 10 days)",
        countLabel: "at-risk shipments",
        formulaLines: [`COUNT(*) WHERE etd_grace_overdue_days BETWEEN -10 AND 0`],
        explanation: `Requests with a Grace ETD that falls within the next 10 days — approaching deadline.`,
        isMonetary: false,
        sumColumn: null,
      },
      shipped: {
        title: "Total Shipped (Payment Processed)",
        countLabel: "completed requests",
        formulaLines: [`COUNT(*) WHERE current_status = 'payment_processed'`],
        explanation: `Requests marked as Payment Processed — the full deposit cycle is complete.`,
        isMonetary: false,
        sumColumn: null,
      },
      yet_to_ship: {
        title: "Yet to Ship (Pending Payment)",
        countLabel: "pending requests",
        formulaLines: [`COUNT(*) WHERE current_status = 'pending_payment'`],
        explanation: `Requests still in Pending Payment state — payment has not yet been processed.`,
        isMonetary: false,
        sumColumn: null,
      },
      active: {
        title: "Total Active Entries",
        countLabel: "active requests",
        formulaLines: [`COUNT(*) WHERE is_deleted = false`],
        explanation: `All non-deleted requests across every status.`,
        isMonetary: false,
        sumColumn: null,
      },
    };
    if (filter && configs[filter]) return { ...configs[filter], isEntity: false };
  }

  // ── Entity sections ─────────────────────────────────────────────────────────
  if (section === "by_merchandiser" && name) {
    return {
      title: name,
      subtitle: "Merchandiser",
      countLabel: "deposit requests",
      formulaLines: [],
      explanation: "",
      isMonetary: false,
      isEntity: true,
      sumColumn: null,
      sectionIcon: <Users className="h-4 w-4 text-muted-foreground" />,
    };
  }

  if (section === "by_vertical" && name) {
    return {
      title: name,
      subtitle: "Vertical / Category",
      countLabel: "deposit requests",
      formulaLines: [],
      explanation: "",
      isMonetary: false,
      isEntity: true,
      sumColumn: null,
      sectionIcon: <BarChart3 className="h-4 w-4 text-muted-foreground" />,
    };
  }

  if (section === "by_customer" && name) {
    return {
      title: name,
      subtitle: "Customer",
      countLabel: "deposit requests",
      formulaLines: [],
      explanation: "",
      isMonetary: false,
      isEntity: true,
      sumColumn: null,
      sectionIcon: <Building2 className="h-4 w-4 text-muted-foreground" />,
    };
  }

  if (section === "delay_buckets" && bucketLabel) {
    return {
      title: `Delay Bucket: ${bucketLabel}`,
      countLabel: "requests in this bucket",
      formulaLines: [],
      explanation: `All deposit requests whose Grace ETD overdue days fall in the "${bucketLabel}" range.`,
      isMonetary: false,
      isEntity: false,
      sumColumn: null,
    };
  }

  return {
    title: "Analytics Drill-Down",
    countLabel: "records",
    formulaLines: [],
    explanation: "",
    isMonetary: false,
    isEntity: false,
    sumColumn: null,
  };
}

// ── Entity summary cards ──────────────────────────────────────────────────────

function EntitySummaryCards({
  rows,
}: {
  rows: { req: DepositRequest; snap: AnalyticsSnapshot | null }[];
}) {
  const overdue = rows.filter(({ snap }) => (snap?.etd_grace_overdue_days ?? 0) > 0);
  const avgDelay = overdue.length > 0
    ? (overdue.reduce((s, { snap }) => s + (snap?.etd_grace_overdue_days ?? 0), 0) / overdue.length).toFixed(1)
    : "—";
  const totalDeposit = rows.reduce((s, { req }) => s + Number(req.deposit_amount ?? 0), 0);
  const totalCostOfFund = rows.reduce((s, { snap }) => s + Number(snap?.cost_of_fund_amount ?? 0), 0);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard label="Total Requests" value={rows.length} icon={ClipboardList} />
      <StatCard label="Overdue Cases" value={overdue.length} icon={AlertTriangle} subtext={overdue.length > 0 ? "Grace ETD exceeded" : "All on track"} />
      <StatCard label="Total Deposit" value={fmtAmt(totalDeposit, "USD")} icon={DollarSign} subtext="across all currencies" />
      <StatCard label="Avg Days Overdue" value={avgDelay === "—" ? "—" : `${avgDelay}d`} icon={Clock} subtext={overdue.length > 0 ? `of ${overdue.length} overdue` : "no overdue"} />
    </div>
  );
}

// ── Delay bucket summary cards ────────────────────────────────────────────────

function BucketSummaryCards({
  rows,
  bucketLabel,
}: {
  rows: { req: DepositRequest; snap: AnalyticsSnapshot | null }[];
  bucketLabel: string;
}) {
  const byCur = rows.reduce<Record<string, number>>((acc, { req }) => {
    const cur = req.currency ?? "USD";
    acc[cur] = (acc[cur] ?? 0) + Number(req.deposit_amount ?? 0);
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard label="Cases" value={rows.length} icon={ClipboardList} subtext={bucketLabel} />
      <StatCard label="Overdue USD" value={fmtAmt(byCur["USD"] ?? 0, "USD")} icon={DollarSign} />
      <StatCard label="Overdue CNY" value={fmtAmt(byCur["CNY"] ?? 0, "CNY")} icon={DollarSign} />
      <StatCard label="Overdue EUR" value={fmtAmt(byCur["EUR"] ?? 0, "EUR")} icon={DollarSign} />
    </div>
  );
}

// ── Pagination ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

// ── Main drill content ────────────────────────────────────────────────────────

function DrillContent() {
  const params = useSearchParams();
  const section   = params.get("section") ?? "";
  const currency  = params.get("currency");
  const metric    = params.get("metric");
  const filter    = params.get("filter");
  const name      = params.get("name");
  const bucketLabel = params.get("label");
  const bucketMin = params.get("min") ? parseInt(params.get("min")!, 10) : null;
  const bucketMax = params.get("max") ? parseInt(params.get("max")!, 10) : null;
  // Cross-filters carried from the analytics tab that linked here
  const xfStaffId    = params.get("staff_id");
  const xfVerticalId = params.get("vertical_id");
  const xfCustomerId = params.get("customer_id");
  const xfEtdMin     = params.get("etd_min") ? parseInt(params.get("etd_min")!, 10) : null;
  const xfEtdMax     = params.get("etd_max") ? parseInt(params.get("etd_max")!, 10) : null;

  const { data: requests = [], isLoading: reqLoading } = useRequests();
  const { data: snapshots = [], isLoading: snapLoading } = useAnalyticsSnapshots();
  const isLoading = reqLoading || snapLoading;

  const meta = getDrillMeta(section, currency, metric, filter, name, bucketLabel);

  const snapshotMap = useMemo(() => {
    const m = new Map<string, AnalyticsSnapshot>();
    snapshots.forEach((s) => m.set(s.deposit_request_id, s));
    return m;
  }, [snapshots]);

  const rows = useMemo(() => {
    const joined = requests.map((req) => ({ req, snap: snapshotMap.get(req.id) ?? null }));

    if (section === "overdue_kpis" && currency) {
      return joined.filter(({ req, snap }) =>
        req.currency === currency && snap !== null && (snap.etd_grace_overdue_days ?? 0) > 0,
      );
    }

    if (section === "shipment_kpis") {
      switch (filter) {
        case "overdue":    return joined.filter(({ snap }) => snap && (snap.etd_grace_overdue_days ?? 0) > 0);
        case "etd_grace":  return joined.filter(({ snap }) => snap && (snap.etd_grace_overdue_days ?? 0) >= -10 && (snap.etd_grace_overdue_days ?? 0) <= 0);
        case "shipped":    return joined.filter(({ req }) => req.current_status === "payment_processed");
        case "yet_to_ship":return joined.filter(({ req }) => req.current_status === "pending_payment");
        case "active":     return joined;
      }
    }

    if (section === "by_merchandiser" && name) {
      return joined.filter(({ req, snap }) => {
        if ((req.creator?.full_name ?? req.creator?.email ?? "Unknown") !== name) return false;
        if (xfVerticalId && req.vertical?.id !== xfVerticalId) return false;
        if (xfCustomerId && req.customer?.id !== xfCustomerId) return false;
        if (xfEtdMin !== null && (snap?.etd_grace_overdue_days ?? 0) <= xfEtdMin) return false;
        if (xfEtdMax !== null && (snap?.etd_grace_overdue_days ?? 0) > xfEtdMax) return false;
        return true;
      });
    }

    if (section === "by_vertical" && name) {
      return joined.filter(({ req, snap }) => {
        if (req.vertical?.name !== name) return false;
        if (xfStaffId && req.created_by !== xfStaffId) return false;
        if (xfCustomerId && req.customer?.id !== xfCustomerId) return false;
        if (xfEtdMin !== null && (snap?.etd_grace_overdue_days ?? 0) <= xfEtdMin) return false;
        if (xfEtdMax !== null && (snap?.etd_grace_overdue_days ?? 0) > xfEtdMax) return false;
        return true;
      });
    }

    if (section === "by_customer" && name) {
      return joined.filter(({ req, snap }) => {
        if (req.customer?.name !== name) return false;
        if (xfStaffId && req.created_by !== xfStaffId) return false;
        if (xfVerticalId && req.vertical?.id !== xfVerticalId) return false;
        if (xfEtdMin !== null && (snap?.etd_grace_overdue_days ?? 0) <= xfEtdMin) return false;
        if (xfEtdMax !== null && (snap?.etd_grace_overdue_days ?? 0) > xfEtdMax) return false;
        return true;
      });
    }

    if (section === "delay_buckets") {
      return joined.filter(({ req, snap }) => {
        const days = snap?.etd_grace_overdue_days ?? 0;
        let matchBucket: boolean;
        if (bucketMin === null && bucketMax !== null) {
          matchBucket = days <= bucketMax;
        } else if (bucketMin !== null && bucketMax !== null) {
          matchBucket = days > bucketMin && days <= bucketMax;
        } else {
          matchBucket = false;
        }
        if (!matchBucket) return false;
        if (xfStaffId && req.created_by !== xfStaffId) return false;
        if (xfVerticalId && req.vertical?.id !== xfVerticalId) return false;
        if (xfCustomerId && req.customer?.id !== xfCustomerId) return false;
        return true;
      });
    }

    return joined;
  }, [requests, snapshotMap, section, currency, metric, filter, name, bucketMin, bucketMax,
      xfStaffId, xfVerticalId, xfCustomerId, xfEtdMin, xfEtdMax]);

  const total = useMemo(() => {
    if (meta.sumColumn === "deposit_amount") return rows.reduce((s, { req }) => s + Number(req.deposit_amount ?? 0), 0);
    if (meta.sumColumn === "cost_of_fund")   return rows.reduce((s, { snap }) => s + Number(snap?.cost_of_fund_amount ?? 0), 0);
    return rows.length;
  }, [rows, meta.sumColumn]);

  const isEntitySection = ["by_merchandiser", "by_vertical", "by_customer"].includes(section);
  const isBucketSection = section === "delay_buckets";

  // ── Filters (entity sections) ───────────────────────────────────────────────
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [staffFilter, setStaffFilter] = useState<string>("all");
  // appliedStaff is only updated when the user clicks "Filter"
  const [appliedStaff, setAppliedStaff] = useState<string>("all");

  // Unique staff members derived from the full (unfiltered) row set
  const staffOptions = useMemo(() => {
    const seen = new Set<string>();
    const opts: { value: string; label: string }[] = [];
    rows.forEach(({ req }) => {
      const val = req.creator?.full_name ?? req.creator?.email ?? "";
      if (val && !seen.has(val)) { seen.add(val); opts.push({ value: val, label: val }); }
    });
    return opts.sort((a, b) => a.label.localeCompare(b.label));
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!isEntitySection) return rows;
    return rows.filter(({ req }) => {
      const matchStatus = statusFilter === "all" || req.current_status === statusFilter;
      const matchStaff  = appliedStaff === "all"
        || (req.creator?.full_name ?? req.creator?.email ?? "") === appliedStaff;
      return matchStatus && matchStaff;
    });
  }, [rows, isEntitySection, statusFilter, appliedStaff]);

  // ── Text search (all sections) ──────────────────────────────────────────────
  const [drillSearch, setDrillSearch] = useState("");
  const drillTerm = drillSearch.trim();
  const preSearchRows = isEntitySection ? filteredRows : rows;
  const displayRows = drillTerm
    ? preSearchRows.filter(({ req }) => requestMatchesSearch(req, drillTerm))
    : preSearchRows;

  // ── Pagination ──────────────────────────────────────────────────────────────
  const [page, setPage] = useState(1);

  // Reset to page 1 whenever the filtered result set changes
  useEffect(() => { setPage(1); }, [displayRows.length, drillTerm, section, currency, filter, name, bucketLabel, statusFilter, appliedStaff]);

  const totalPages = Math.max(1, Math.ceil(displayRows.length / PAGE_SIZE));
  const pagedRows  = displayRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-6">
      {/* Back + title */}
      <div>
        <Link
          href={`/analytics?tab=${section ?? "overview"}`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Analytics
        </Link>
        {meta.subtitle && (
          <div className="flex items-center gap-2 mb-1">
            {meta.sectionIcon}
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{meta.subtitle}</span>
          </div>
        )}
        <h1 className="text-xl font-bold text-foreground">{meta.title}</h1>
        {!isLoading && (
          <p className="text-sm text-muted-foreground mt-1">
            <span className="font-semibold text-foreground">{displayRows.length}</span>{" "}
            {meta.countLabel}
            {meta.isMonetary && (
              <>
                {" · "}
                <span className="font-semibold text-foreground">
                  {fmtAmt(total, meta.sumCurrency ?? "USD")} {meta.sumCurrency}
                </span>{" "}
                total
              </>
            )}
          </p>
        )}
      </div>

      {/* Entity summary cards */}
      {!isLoading && isEntitySection && <EntitySummaryCards rows={rows} />}

      {/* Delay bucket summary cards */}
      {!isLoading && isBucketSection && bucketLabel && (
        <BucketSummaryCards rows={rows} bucketLabel={bucketLabel} />
      )}

      {/* Formula box (KPI sections only) */}
      {meta.formulaLines.length > 0 && (
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Info className="h-4 w-4 text-muted-foreground" />
              How this number was derived
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Database Query</p>
                <pre className="bg-muted rounded-lg px-4 py-3 text-xs font-mono text-foreground leading-relaxed overflow-x-auto">
                  {meta.formulaLines.join("\n")}
                </pre>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Plain English</p>
                <p className="text-sm text-muted-foreground leading-relaxed">{meta.explanation}</p>
              </div>
            </div>
            {meta.sumColumn && (
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">KPI Formula: </span>
                  {meta.sumColumn === "deposit_amount"
                    ? "KPI Total = SUM of the \"Deposit Amount\" column in the table below."
                    : "KPI Total = SUM of the \"Cost of Fund\" column in the table below."}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Plain explanation (bucket / entity with explanation) */}
      {!meta.formulaLines.length && meta.explanation && (
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground mb-2">
              <Info className="h-4 w-4 text-muted-foreground" />
              About this view
            </div>
            <p className="text-sm text-muted-foreground">{meta.explanation}</p>
          </CardContent>
        </Card>
      )}

      {/* Data table */}
      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex flex-wrap items-center gap-2">
          <Hash className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-semibold text-foreground text-sm shrink-0">
            {isEntitySection ? "All Requests" : "Contributing Records"}
          </span>
          {isEntitySection && (
            <>
              {/* Staff member picker — only show for vertical/customer drill-downs where staff varies */}
              {section !== "by_merchandiser" && staffOptions.length > 1 && (
                <select
                  value={staffFilter}
                  onChange={(e) => setStaffFilter(e.target.value)}
                  className="text-xs border border-border rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-foreground/30"
                >
                  <option value="all">All staff</option>
                  {staffOptions.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              )}
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-xs border border-border rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-foreground/30"
              >
                <option value="all">All statuses</option>
                <option value="pending_payment">Pending Payment</option>
                <option value="payment_processed">Payment Processed</option>
                <option value="cancelled_by_merchandiser">Cancelled by Merchandiser</option>
                <option value="cancelled_by_accounts">Cancelled by Accounts</option>
                <option value="hold_by_merchandiser">Hold by Merchandiser</option>
                <option value="hold_by_accounts">Hold by Accounts</option>
              </select>
              <button
                onClick={() => setAppliedStaff(staffFilter)}
                className="text-xs font-medium px-3 py-1.5 rounded-md bg-foreground text-background hover:opacity-80 transition-opacity"
              >
                Filter
              </button>
              {(appliedStaff !== "all" || statusFilter !== "all") && (
                <button
                  onClick={() => { setStatusFilter("all"); setStaffFilter("all"); setAppliedStaff("all"); }}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2"
                >
                  Clear
                </button>
              )}
            </>
          )}
          <SearchInput
            value={drillSearch}
            onChange={setDrillSearch}
            placeholder="Search requests…"
            className="w-full sm:w-56 sm:ml-auto"
          />
          {!isLoading && (
            <span className="text-xs text-muted-foreground tabular-nums shrink-0">
              {displayRows.length.toLocaleString()} row{displayRows.length !== 1 ? "s" : ""}
              {(drillTerm || (isEntitySection && (appliedStaff !== "all" || statusFilter !== "all"))) && ` (of ${rows.length.toLocaleString()})`}
            </span>
          )}
        </div>

        {/* Mobile card list */}
        <div className="md:hidden divide-y divide-border" id="drill-table-top">
          {isLoading ? (
            <div className="p-4 text-sm text-muted-foreground text-center">Loading…</div>
          ) : pagedRows.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No records match this view.{" "}
              <Link href={`/analytics?tab=${section ?? "overview"}`} className="underline underline-offset-2 hover:text-foreground">Return to Analytics</Link>
            </div>
          ) : pagedRows.map(({ req, snap }) => (
            <div key={req.id} className="p-4 space-y-2.5">
              <div className="flex items-start justify-between gap-2">
                <Link
                  href={`/accounts/${req.id}`}
                  className="font-mono text-xs font-bold text-foreground hover:underline underline-offset-2"
                >
                  {req.request_number}
                </Link>
                {req.current_status && <StatusBadge status={req.current_status as RequestStatus} />}
              </div>
              <div className="text-sm font-semibold text-foreground">{req.supplier?.name ?? "—"}</div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                {req.customer?.name && <span>{req.customer.name}</span>}
                {req.vertical?.name && <span>· {req.vertical.name}</span>}
              </div>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="font-bold text-foreground">{fmtAmt(req.deposit_amount, req.currency)} <span className="text-xs font-normal text-muted-foreground">{req.currency}</span></span>
                {(snap?.etd_grace_overdue_days ?? 0) > 0 && (
                  <span className="text-xs font-semibold text-foreground tabular-nums">{snap!.etd_grace_overdue_days}d overdue</span>
                )}
              </div>
            </div>
          ))}
          {!isLoading && displayRows.length > PAGE_SIZE && (
            <div className="px-4">
              <Pagination page={page} totalPages={totalPages} total={displayRows.length} pageSize={PAGE_SIZE}
                onChange={(p) => { setPage(p); document.getElementById("drill-table-top")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}
              />
            </div>
          )}
        </div>

        {/* Desktop table */}
        <div className="hidden md:block overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Request #</TableHead>
                <TableHead>Supplier</TableHead>
                {section !== "by_customer"     && <TableHead className="hidden md:table-cell">Customer</TableHead>}
                {section !== "by_vertical"     && <TableHead className="hidden lg:table-cell">Vertical</TableHead>}
                {section === "by_merchandiser" && <TableHead className="hidden lg:table-cell">Merchandiser</TableHead>}
                <TableHead className="text-right">Currency</TableHead>
                <TableHead className={cn("text-right", meta.sumColumn === "deposit_amount" && "font-bold text-foreground")}>Deposit Amount</TableHead>
                <TableHead className="text-right hidden md:table-cell">Grace ETD</TableHead>
                <TableHead className="text-right">Days Overdue</TableHead>
                <TableHead className={cn("text-right hidden lg:table-cell", meta.sumColumn === "cost_of_fund" && "font-bold text-foreground")}>Cost of Fund</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden lg:table-cell">Submitted</TableHead>
                {meta.isMonetary && <TableHead className="text-right hidden md:table-cell">Contribution</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableSkeleton rows={8} cols={meta.isMonetary ? 12 : 11} />
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={12} className="text-center py-16 text-sm text-muted-foreground">
                    No records match this view.{" "}
                    <Link href="/analytics" className="underline underline-offset-2 hover:text-foreground">
                      Return to Analytics
                    </Link>
                  </TableCell>
                </TableRow>
              ) : (
                <>
                  {pagedRows.map(({ req, snap }) => {
                    const rowValue =
                      meta.sumColumn === "deposit_amount"  ? req.deposit_amount
                      : meta.sumColumn === "cost_of_fund" ? (snap?.cost_of_fund_amount ?? 0)
                      : null;

                    return (
                      <TableRow key={req.id} className="hover:bg-muted/30">
                        <TableCell>
                          <Link
                            href={`/accounts/${req.id}`}
                            className="font-mono text-xs font-semibold text-foreground hover:underline underline-offset-2"
                          >
                            {req.request_number}
                          </Link>
                        </TableCell>
                        <TableCell className="font-medium text-sm text-foreground">{req.supplier?.name ?? "—"}</TableCell>
                        {section !== "by_customer"     && <TableCell className="hidden md:table-cell text-muted-foreground text-sm">{req.customer?.name ?? "—"}</TableCell>}
                        {section !== "by_vertical"     && <TableCell className="hidden lg:table-cell text-muted-foreground text-sm">{req.vertical?.name ?? "—"}</TableCell>}
                        {section === "by_merchandiser" && <TableCell className="hidden lg:table-cell text-muted-foreground text-sm">{req.creator?.full_name ?? "—"}</TableCell>}
                        <TableCell className="text-right tabular-nums text-sm">{req.currency}</TableCell>
                        <TableCell className={cn("text-right tabular-nums font-medium", meta.sumColumn === "deposit_amount" ? "text-foreground" : "text-muted-foreground")}>
                          {fmtAmt(req.deposit_amount, req.currency)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground text-sm hidden md:table-cell">
                          {snap?.grace_etd ? formatDate(snap.grace_etd) : "—"}
                        </TableCell>
                        <TableCell className={cn("text-right tabular-nums", (snap?.etd_grace_overdue_days ?? 0) > 0 ? "font-semibold text-foreground" : "text-muted-foreground")}>
                          {snap?.etd_grace_overdue_days != null ? `${snap.etd_grace_overdue_days}d` : "—"}
                        </TableCell>
                        <TableCell className={cn("text-right tabular-nums hidden lg:table-cell", meta.sumColumn === "cost_of_fund" ? "font-semibold text-foreground" : "text-muted-foreground")}>
                          {snap?.cost_of_fund_amount != null ? fmtAmt(snap.cost_of_fund_amount, req.currency) : "—"}
                        </TableCell>
                        <TableCell>
                          {req.current_status ? <StatusBadge status={req.current_status as RequestStatus} /> : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs hidden lg:table-cell">{formatDate(req.created_at)}</TableCell>
                        {meta.isMonetary && (
                          <TableCell className="text-right tabular-nums text-muted-foreground hidden md:table-cell">
                            {rowValue != null ? fmtPct(rowValue, total) : "—"}
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}

                  {/* Totals row for monetary KPIs — always shows the grand total across all pages */}
                  {meta.isMonetary && (
                    <TableRow className="border-t-2 border-border bg-muted/40 font-semibold">
                      <TableCell colSpan={5} className="text-sm">Total ({displayRows.length.toLocaleString()} records)</TableCell>
                      <TableCell className={cn("text-right tabular-nums", meta.sumColumn === "deposit_amount" ? "text-foreground" : "text-muted-foreground")}>
                        {meta.sumColumn === "deposit_amount" ? fmtAmt(total, meta.sumCurrency) : "—"}
                      </TableCell>
                      <TableCell className="hidden md:table-cell" />
                      <TableCell />
                      <TableCell className={cn("text-right tabular-nums hidden lg:table-cell", meta.sumColumn === "cost_of_fund" ? "text-foreground" : "text-muted-foreground")}>
                        {meta.sumColumn === "cost_of_fund" ? fmtAmt(total, meta.sumCurrency) : "—"}
                      </TableCell>
                      <TableCell />
                      <TableCell className="hidden lg:table-cell" />
                      <TableCell className="text-right tabular-nums hidden md:table-cell">100%</TableCell>
                    </TableRow>
                  )}
                </>
              )}
            </TableBody>
          </Table>
        </div>
        {/* Pagination bar — shown inside the card, below the table */}
        {!isLoading && displayRows.length > PAGE_SIZE && (
          <div className="px-4">
            <Pagination
              page={page}
              totalPages={totalPages}
              total={displayRows.length}
              pageSize={PAGE_SIZE}
              onChange={(p) => {
                setPage(p);
                document.getElementById("drill-table-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Page shell ────────────────────────────────────────────────────────────────

export default function DrillPage() {
  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"]}>
      <TopNav title="Analytics Drill-Down" />
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <Suspense
          fallback={
            <div className="space-y-6">
              <Skeleton className="h-8 w-48" />
              <Skeleton className="h-32 rounded-xl" />
              <Skeleton className="h-64 rounded-xl" />
            </div>
          }
        >
          <DrillContent />
        </Suspense>
      </main>
    </RoleGuard>
  );
}

"use client";

// Projections module (4 Sep 2026): every month the merchandisers project the
// deposits they expect to request per vertical (USD / EUR / CNY). The window
// runs from the 25th to the end of the month and collects the NEXT month;
// after the deadline only the Super Admin can add values (on behalf — the
// unblock path: a merchandiser missing the current month's projections
// cannot raise new requests). The dashboard compares projections against
// the month's actual requested deposit amounts.

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { toast } from "sonner";

// Recharts is heavy — load the analysis chart only when the page renders.
const ProjectionChart = dynamic(
  () => import("@/components/charts/ProjectionChart").then((m) => ({ default: m.ProjectionChart })),
  { ssr: false },
);
import { AlertTriangle, CalendarClock, LineChart, UserCog } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/hooks/useAuth";
import { useMerchandiserOptions, useVerticals } from "@/hooks/useMasters";
import {
  useProjectionDashboard,
  useProjectionStatus,
  useSubmitProjections,
} from "@/hooks/useProjections";
import { formatDate } from "@/lib/utils";
import type { ProjectionSubmitItem } from "@/services/projectionService";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const inputCls =
  "flex h-8 w-28 rounded-md border border-input bg-background px-2 py-1 text-xs text-right focus:outline-none focus:ring-1 focus:ring-ring";
const selectCls =
  "flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

type Draft = Record<string, { usd: string; eur: string; cny: string }>;

function fmt(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2 });
}

function AmountInputs({
  value,
  onChange,
}: {
  value: { usd: string; eur: string; cny: string };
  onChange: (v: { usd: string; eur: string; cny: string }) => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {(["usd", "eur", "cny"] as const).map((cur) => (
        <label key={cur} className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          {cur.toUpperCase()}
          <input
            type="number"
            step="0.01"
            min="0"
            value={value[cur]}
            onChange={(e) => onChange({ ...value, [cur]: e.target.value })}
            className={inputCls}
          />
        </label>
      ))}
    </div>
  );
}

function toItems(verticalIds: string[], draft: Draft): ProjectionSubmitItem[] {
  return verticalIds.map((id) => ({
    vertical_id: id,
    amount_usd: Number(draft[id]?.usd) || 0,
    amount_eur: Number(draft[id]?.eur) || 0,
    amount_cny: Number(draft[id]?.cny) || 0,
  }));
}

// ── Merchandiser: my projections form ────────────────────────────────────────

function MyProjectionsForm() {
  const { data: status } = useProjectionStatus();
  const submit = useSubmitProjections();
  const [draft, setDraft] = useState<Draft>({});
  const [seeded, setSeeded] = useState(false);

  if (!status || !status.has_verticals) return null;

  // Seed the draft once from the already-filled values.
  if (!seeded && status.verticals.length > 0) {
    const initial: Draft = {};
    for (const v of status.verticals) {
      initial[v.vertical_id] = {
        usd: v.amount_usd != null ? String(v.amount_usd) : "",
        eur: v.amount_eur != null ? String(v.amount_eur) : "",
        cny: v.amount_cny != null ? String(v.amount_cny) : "",
      };
    }
    setDraft(initial);
    setSeeded(true);
  }

  const monthLabel = `${MONTHS[status.target_month - 1]} ${status.target_year}`;

  const doSubmit = async () => {
    try {
      await submit.mutateAsync({
        year: status.target_year,
        month: status.target_month,
        items: toItems(status.verticals.map((v) => v.vertical_id), draft),
      });
      toast.success(`${monthLabel} projections saved.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save the projections.");
    }
  };

  return (
    <Card>
      <CardContent className="p-5 md:p-6 space-y-4">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-muted-foreground" />
          <h2 className="font-semibold text-foreground text-sm">
            My Projections — {monthLabel}
          </h2>
        </div>
        {status.blocked && (
          <p className="text-sm text-red-800 bg-red-50 border border-red-200 rounded-lg p-3">
            {status.block_message}
          </p>
        )}
        {status.window_open ? (
          <p className="text-xs text-muted-foreground">
            The window closes on {formatDate(status.window_ends)}. Fill each vertical&apos;s
            projected deposits — you can update them until the deadline.
            {status.missing_target.length > 0 &&
              ` Still missing: ${status.missing_target.join(", ")}.`}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            The projection window opens on the 25th of the month. After the deadline only the
            Super Admin can add values on your behalf.
          </p>
        )}
        <div className="space-y-3">
          {status.verticals.map((v) => (
            <div key={v.vertical_id} className="flex flex-col sm:flex-row sm:items-center gap-2">
              <span className="text-sm font-medium text-foreground sm:w-56">
                {v.name}
                {!v.filled && <span className="text-amber-700 text-xs ml-1.5">(pending)</span>}
              </span>
              <AmountInputs
                value={draft[v.vertical_id] ?? { usd: "", eur: "", cny: "" }}
                onChange={(val) => setDraft((d) => ({ ...d, [v.vertical_id]: val }))}
              />
            </div>
          ))}
        </div>
        <Button onClick={doSubmit} disabled={!status.window_open || submit.isPending}>
          {submit.isPending ? "Saving…" : `Save ${monthLabel} Projections`}
        </Button>
      </CardContent>
    </Card>
  );
}

// ── Super Admin: on-behalf entry (the unblock path) ──────────────────────────

function OnBehalfForm() {
  const today = new Date();
  const { data: merchandisers = [] } = useMerchandiserOptions();
  const { data: verticals = [] } = useVerticals();
  const submit = useSubmitProjections();
  const [userId, setUserId] = useState("");
  const [period, setPeriod] = useState("current");
  const [draft, setDraft] = useState<Draft>({});

  const current = { year: today.getFullYear(), month: today.getMonth() + 1 };
  const next =
    current.month === 12
      ? { year: current.year + 1, month: 1 }
      : { year: current.year, month: current.month + 1 };
  const target = period === "current" ? current : next;

  const userVerticals = useMemo(
    () => verticals.filter((v) => v.assigned_user_id === userId),
    [verticals, userId],
  );

  const doSubmit = async () => {
    try {
      await submit.mutateAsync({
        year: target.year,
        month: target.month,
        items: toItems(userVerticals.map((v) => v.id), draft),
      });
      toast.success(
        `${MONTHS[target.month - 1]} ${target.year} projections saved on behalf of the merchandiser — they are unblocked once the current month is complete.`,
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save the projections.");
    }
  };

  return (
    <Card>
      <CardContent className="p-5 md:p-6 space-y-4">
        <div className="flex items-center gap-2">
          <UserCog className="h-4 w-4 text-muted-foreground" />
          <h2 className="font-semibold text-foreground text-sm">
            Add Projections on Behalf (Super Admin)
          </h2>
        </div>
        <p className="text-xs text-muted-foreground">
          A merchandiser who missed the deadline is blocked from raising requests until the
          CURRENT month&apos;s projections are complete — fill them here to unblock.
        </p>
        <div className="flex flex-wrap gap-3">
          <select value={userId} onChange={(e) => { setUserId(e.target.value); setDraft({}); }} className={selectCls}>
            <option value="">Select merchandiser</option>
            {merchandisers.map((m) => (
              <option key={m.id} value={m.id}>{m.full_name}</option>
            ))}
          </select>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} className={selectCls}>
            <option value="current">
              {MONTHS[current.month - 1]} {current.year} (current — unblocks)
            </option>
            <option value="next">
              {MONTHS[next.month - 1]} {next.year} (next month)
            </option>
          </select>
        </div>
        {userId && userVerticals.length === 0 && (
          <p className="text-xs text-amber-700">
            No verticals are assigned to this merchandiser — assign them on the Team Members page first.
          </p>
        )}
        {userVerticals.map((v) => (
          <div key={v.id} className="flex flex-col sm:flex-row sm:items-center gap-2">
            <span className="text-sm font-medium text-foreground sm:w-56">{v.name}</span>
            <AmountInputs
              value={draft[v.id] ?? { usd: "", eur: "", cny: "" }}
              onChange={(val) => setDraft((d) => ({ ...d, [v.id]: val }))}
            />
          </div>
        ))}
        {userVerticals.length > 0 && (
          <Button onClick={doSubmit} disabled={submit.isPending}>
            {submit.isPending ? "Saving…" : "Save Projections"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ── Dashboard: projection vs actual ──────────────────────────────────────────

function ProjectionDashboard() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  // Analysis view (5 Sep 2026): which currency the bar chart plots.
  const [chartCurrency, setChartCurrency] = useState<"usd" | "eur" | "cny">("usd");
  const { data, isLoading } = useProjectionDashboard(year, month);
  const rows = data?.rows ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      proj_usd: acc.proj_usd + r.proj_usd, actual_usd: acc.actual_usd + r.actual_usd,
      proj_eur: acc.proj_eur + r.proj_eur, actual_eur: acc.actual_eur + r.actual_eur,
      proj_cny: acc.proj_cny + r.proj_cny, actual_cny: acc.actual_cny + r.actual_cny,
    }),
    { proj_usd: 0, actual_usd: 0, proj_eur: 0, actual_eur: 0, proj_cny: 0, actual_cny: 0 },
  );

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-foreground text-sm">Projections vs Actuals</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Actuals = deposit amounts of live requests raised in the month, per vertical.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))} className={selectCls}>
            {MONTHS.map((m, i) => (
              <option key={m} value={i + 1}>{m}</option>
            ))}
          </select>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} className={selectCls}>
            {[today.getFullYear() + 1, today.getFullYear(), today.getFullYear() - 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>
      {/* Analysis view (5 Sep 2026): achievement strip + grouped bar chart
          per currency, with the detail table below. */}
      {!isLoading && rows.length > 0 && (
        <div className="px-5 py-4 border-b border-border space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="grid grid-cols-3 gap-4">
              {(() => {
                const proj = totals[`proj_${chartCurrency}`];
                const actual = totals[`actual_${chartCurrency}`];
                const pct = proj > 0 ? (actual / proj) * 100 : null;
                const cur = chartCurrency.toUpperCase();
                return (
                  <>
                    <div>
                      <p className="text-xs text-muted-foreground">Projected ({cur})</p>
                      <p className="text-sm font-semibold text-foreground tabular-nums">{fmt(proj)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Actual ({cur})</p>
                      <p className="text-sm font-semibold text-foreground tabular-nums">{fmt(actual)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Achievement</p>
                      <p className={`text-sm font-semibold tabular-nums ${pct == null ? "text-muted-foreground" : pct >= 100 ? "text-emerald-700" : "text-amber-700"}`}>
                        {pct == null ? "—" : `${pct.toFixed(1)}%`}
                      </p>
                    </div>
                  </>
                );
              })()}
            </div>
            <div className="flex items-center gap-1">
              {(["usd", "eur", "cny"] as const).map((c) => (
                <Button
                  key={c}
                  size="sm"
                  variant={chartCurrency === c ? "default" : "outline"}
                  onClick={() => setChartCurrency(c)}
                >
                  {c.toUpperCase()}
                </Button>
              ))}
            </div>
          </div>
          <ProjectionChart rows={rows} currency={chartCurrency} />
        </div>
      )}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Vertical</TableHead>
              <TableHead>Merchandiser</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Proj USD</TableHead>
              <TableHead className="text-right">Actual USD</TableHead>
              <TableHead className="text-right hidden md:table-cell">Proj EUR</TableHead>
              <TableHead className="text-right hidden md:table-cell">Actual EUR</TableHead>
              <TableHead className="text-right hidden md:table-cell">Proj CNY</TableHead>
              <TableHead className="text-right hidden md:table-cell">Actual CNY</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeleton rows={6} cols={9} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  <EmptyState
                    icon={LineChart}
                    title="No projections for this month"
                    description="Assigned verticals and their filled projections will appear here."
                  />
                </td>
              </tr>
            ) : (
              <>
                {rows.map((r) => (
                  <TableRow key={r.vertical_id}>
                    <TableCell className="font-medium text-sm">{r.vertical}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.merchandiser ?? "—"}</TableCell>
                    <TableCell>
                      {r.filled ? (
                        <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">Filled</span>
                      ) : (
                        <span className="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Pending</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{fmt(r.proj_usd)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm font-medium">{fmt(r.actual_usd)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(r.proj_eur)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm font-medium hidden md:table-cell">{fmt(r.actual_eur)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(r.proj_cny)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm font-medium hidden md:table-cell">{fmt(r.actual_cny)}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/60 hover:bg-muted/60 font-semibold">
                  <TableCell colSpan={3} className="text-sm">Total</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{fmt(totals.proj_usd)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{fmt(totals.actual_usd)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(totals.proj_eur)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(totals.actual_eur)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(totals.proj_cny)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm hidden md:table-cell">{fmt(totals.actual_cny)}</TableCell>
                </TableRow>
              </>
            )}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

export default function ProjectionsPage() {
  const { user } = useAuth();
  const isMerchandiser = user?.role === "merchandiser";
  const isSuperAdmin = user?.role === "super_admin";
  const { data: status } = useProjectionStatus(isMerchandiser);

  return (
    <RoleGuard allowedRoles={["merchandiser", "accounts_team", "super_admin", "finance_admin", "head_of_merchandiser"]}>
      <TopNav
        title="Projections"
        subtitle="Monthly deposit projections per vertical — filled from the 25th for the coming month, compared against actual requests"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-6xl mx-auto w-full">
        {isMerchandiser && status?.blocked && (
          <p className="text-sm text-red-800 bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            {status.block_message}
          </p>
        )}
        {isMerchandiser && <MyProjectionsForm />}
        {isSuperAdmin && <OnBehalfForm />}
        <ProjectionDashboard />
      </main>
    </RoleGuard>
  );
}

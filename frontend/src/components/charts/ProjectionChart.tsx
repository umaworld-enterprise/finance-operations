"use client";

// Projections analysis chart (5 Sep 2026): grouped bars — Projected vs
// Actual per vertical for the selected month and currency. Rendered above
// the projections table; lazy-loaded from the page like the other charts.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProjectionDashboardRow } from "@/services/projectionService";

interface Props {
  rows: ProjectionDashboardRow[];
  /** Which currency's pair of bars to plot. */
  currency: "usd" | "eur" | "cny";
}

const fmt = (v: number) =>
  v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `${(v / 1_000).toFixed(0)}K` : String(v);

export function ProjectionChart({ rows, currency }: Props) {
  const data = rows
    .map((r) => ({
      vertical: r.vertical,
      Projected: r[`proj_${currency}`],
      Actual: r[`actual_${currency}`],
    }))
    .filter((d) => d.Projected > 0 || d.Actual > 0);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-56 text-muted-foreground text-sm">
        No {currency.toUpperCase()} projections or actuals for this month
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(280, 40 + data.length * 18)}>
      <BarChart data={data} margin={{ left: 8, right: 16, top: 4, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(0 0% 90%)" />
        <XAxis
          dataKey="vertical"
          tick={{ fontSize: 10, fill: "hsl(0 0% 45%)" }}
          interval={0}
          angle={-30}
          textAnchor="end"
          height={70}
        />
        <YAxis tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }} tickFormatter={fmt} width={56} />
        <Tooltip
          formatter={(v: number, name: string) => [
            v.toLocaleString("en-US", { minimumFractionDigits: 2 }),
            `${name} (${currency.toUpperCase()})`,
          ]}
          contentStyle={{ fontSize: 12, border: "1px solid hsl(0 0% 90%)", borderRadius: 8, background: "hsl(0 0% 100%)" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="Projected" fill="hsl(215 60% 60%)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Actual" fill="hsl(150 55% 42%)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { AnalyticsSnapshot } from "@/types";
import { formatCurrency } from "@/lib/utils";

interface Props {
  snapshots: AnalyticsSnapshot[];
}

export function CostOfFundChart({ snapshots }: Props) {
  const data = snapshots
    .filter((s) => (s.cost_of_fund_amount ?? 0) > 0)
    .sort((a, b) => (b.cost_of_fund_amount ?? 0) - (a.cost_of_fund_amount ?? 0))
    .slice(0, 15)
    .map((s) => ({
      label: s.request_number ?? s.deposit_request_id.slice(0, 8),
      amount: Number(s.cost_of_fund_amount ?? 0),
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        No cost of fund exposure
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(0 0% 90%)" />
        <XAxis
          type="number"
          tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }} width={90} />
        <Tooltip
          formatter={(v: number) => [formatCurrency(v, "USD"), "Cost of Fund"]}
          contentStyle={{ fontSize: 12, border: "1px solid hsl(0 0% 90%)", borderRadius: 8, background: "hsl(0 0% 100%)" }}
        />
        <Bar dataKey="amount" fill="hsl(221 83% 53%)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

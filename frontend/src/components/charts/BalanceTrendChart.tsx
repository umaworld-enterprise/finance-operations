"use client";

// Daily closing-balance trend for one bank statement (Banking module,
// Aug 2026) — built from the statement's per-day CLOSING BALANCE rows.

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate } from "@/lib/utils";
import type { BankDailyBalance } from "@/types";

function fmtCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(0)}k`;
  return v.toFixed(0);
}

export function BalanceTrendChart({
  balances,
  currency,
}: {
  balances: BankDailyBalance[];
  currency: string | null;
}) {
  if (balances.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        No daily balances extracted
      </div>
    );
  }
  const data = [...balances]
    .sort((a, b) => a.balance_date.localeCompare(b.balance_date))
    .map((b) => ({
      date: formatDate(b.balance_date),
      balance: Number(b.closing_balance),
    }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ left: 12, right: 16, top: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(0 0% 90%)" />
        <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(0 0% 45%)" }} minTickGap={24} />
        <YAxis
          tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }}
          tickFormatter={fmtCompact}
          width={56}
          domain={["auto", "auto"]}
        />
        <Tooltip
          formatter={(value: number) => [
            `${currency ?? ""} ${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`.trim(),
            "Closing balance",
          ]}
          contentStyle={{
            fontSize: 12,
            border: "1px solid hsl(0 0% 90%)",
            borderRadius: 8,
            background: "hsl(0 0% 100%)",
          }}
        />
        <Line
          type="monotone"
          dataKey="balance"
          stroke="hsl(221 83% 53%)"
          strokeWidth={2}
          dot={{ r: 2, fill: "hsl(221 83% 53%)" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

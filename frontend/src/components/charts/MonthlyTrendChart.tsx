"use client";

import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface MonthlyTrendPoint {
  month: number;
  month_name: string;
  total_overdue_days: number;
  total_cost_of_fund: number;
  ytd_overdue_days: number;
  ytd_cost_of_fund: number;
  request_count: number;
}

interface Props {
  data: MonthlyTrendPoint[];
  metric: "overdue" | "cost_of_fund";
}

function fmtValue(metric: Props["metric"], v: number) {
  if (metric === "cost_of_fund") {
    if (v === 0) return "$0";
    if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`;
    return `$${v.toFixed(0)}`;
  }
  return `${v}d`;
}

export function MonthlyTrendChart({ data, metric }: Props) {
  const momKey  = metric === "overdue" ? "total_overdue_days"  : "total_cost_of_fund";
  const ytdKey  = metric === "overdue" ? "ytd_overdue_days"    : "ytd_cost_of_fund";
  const barFill = metric === "overdue" ? "hsl(0 72% 51%)"      : "hsl(221 83% 53%)";

  const hasData = data.some((d) => (d[momKey] as number) > 0);

  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        No data for selected year
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data} margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(0 0% 90%)" />
        <XAxis
          dataKey="month_name"
          tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }}
        />
        <YAxis
          yAxisId="mom"
          tick={{ fontSize: 11, fill: "hsl(0 0% 45%)" }}
          tickFormatter={(v) => fmtValue(metric, v)}
          width={metric === "cost_of_fund" ? 52 : 38}
        />
        <YAxis
          yAxisId="ytd"
          orientation="right"
          tick={{ fontSize: 11, fill: "hsl(0 0% 60%)" }}
          tickFormatter={(v) => fmtValue(metric, v)}
          width={metric === "cost_of_fund" ? 52 : 38}
        />
        <Tooltip
          formatter={(value: number, name: string) => [
            fmtValue(metric, value),
            name === momKey ? "MoM" : "YTD",
          ]}
          contentStyle={{
            fontSize: 12,
            border: "1px solid hsl(0 0% 90%)",
            borderRadius: 8,
            background: "hsl(0 0% 100%)",
          }}
        />
        <Legend
          formatter={(val) => (val === momKey ? "Monthly" : "YTD Cumulative")}
          wrapperStyle={{ fontSize: 11 }}
        />
        <Bar
          yAxisId="mom"
          dataKey={momKey}
          fill={barFill}
          radius={[3, 3, 0, 0]}
          maxBarSize={32}
        />
        <Line
          yAxisId="ytd"
          type="monotone"
          dataKey={ytdKey}
          stroke="hsl(0 0% 50%)"
          strokeWidth={1.5}
          dot={{ r: 2, fill: "hsl(0 0% 50%)" }}
          strokeDasharray="4 2"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

"use client";

// Single-statement dashboard (Banking module, Aug 2026): summary KPIs,
// daily closing-balance trend, breakdown by transaction type, and the full
// searchable transaction list. All figures computed from the extracted rows.

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowDownCircle, ArrowLeft, ArrowUpCircle, FileQuestion, Landmark,
  Loader2, ReceiptText, Scale, Wallet,
} from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { TableControls } from "@/components/ui/TableControls";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { BalanceTrendChart } from "@/components/charts/BalanceTrendChart";
import { useBankStatement } from "@/hooks/useBankStatements";
import { byNumber, byString, useClientTable } from "@/hooks/useClientTable";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { BankTransaction } from "@/types";

const TXN_SORTS = [
  { value: "date", label: "Date (oldest first)", compare: byString<BankTransaction>((t) => t.txn_date ?? "") },
  { value: "date-desc", label: "Date (newest first)", compare: byString<BankTransaction>((t) => t.txn_date ?? "", true) },
  { value: "amount", label: "Amount (high → low)", compare: byNumber<BankTransaction>((t) => Number(t.debit ?? t.credit ?? 0), true) },
  { value: "category", label: "Type (A–Z)", compare: byString<BankTransaction>((t) => t.category ?? "") },
];

export default function BankStatementDashboard() {
  const { id } = useParams<{ id: string }>();
  const { data: statement, isLoading } = useBankStatement(id);

  const transactions = statement?.transactions ?? [];
  const table = useClientTable(transactions, {
    searchHaystack: (t) => [t.category, t.reference, t.detail],
    sortOptions: TXN_SORTS,
    pageSize: 25,
  });

  if (isLoading) {
    return (
      <>
        <TopNav title="Bank Statement" />
        <main className="flex-1 overflow-auto p-4 md:p-6 space-y-4">
          <Skeleton className="h-4 w-40" />
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <Skeleton className="h-64" />
        </main>
      </>
    );
  }

  if (!statement) {
    return (
      <>
        <TopNav title="Bank Statement" />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <EmptyState
            icon={FileQuestion}
            title="Statement not found"
            action={<Button asChild variant="outline"><Link href="/bank">Back to statements</Link></Button>}
          />
        </main>
      </>
    );
  }

  const currency = statement.currency;
  const totalDebits = transactions.reduce((s, t) => s + Number(t.debit ?? 0), 0);
  const totalCredits = transactions.reduce((s, t) => s + Number(t.credit ?? 0), 0);
  const net = totalCredits - totalDebits;
  const integrityOk = (statement.extraction_note ?? "").includes("passed");

  // Breakdown by the statement's own transaction-type lines.
  const byCategory = new Map<string, { count: number; debit: number; credit: number }>();
  for (const t of transactions) {
    const key = t.category ?? "Uncategorised";
    const row = byCategory.get(key) ?? { count: 0, debit: 0, credit: 0 };
    row.count += 1;
    row.debit += Number(t.debit ?? 0);
    row.credit += Number(t.credit ?? 0);
    byCategory.set(key, row);
  }
  const categories = [...byCategory.entries()].sort(
    (a, b) => b[1].debit + b[1].credit - (a[1].debit + a[1].credit),
  );

  return (
    <RoleGuard allowedRoles={["super_admin", "accounts_team"]}>
      <TopNav
        title={`${statement.bank_name} — ${statement.account_number ?? statement.original_filename}`}
        subtitle={
          statement.period_start
            ? `Statement period ${formatDate(statement.period_start)} to ${formatDate(statement.period_end)}`
            : statement.original_filename
        }
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        <Link
          href="/bank"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to statements
        </Link>

        {statement.status === "processing" && (
          <div className="rounded-lg bg-amber-50 border border-amber-300 text-amber-800 p-3 text-sm flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Extraction is still running — figures below update automatically as pages finish.
          </div>
        )}
        {statement.status === "failed" && (
          <div className="rounded-lg bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
            Extraction failed: {statement.extraction_note ?? "unknown error"}. Delete the
            statement and upload the PDF again.
          </div>
        )}
        {statement.status === "extracted" && statement.extraction_note && (
          <div
            className={`rounded-lg border p-3 text-sm ${
              integrityOk
                ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                : "bg-amber-50 border-amber-300 text-amber-800"
            }`}
          >
            {statement.extraction_note}
          </div>
        )}

        {/* Summary KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <StatCard
            label="Opening Balance"
            value={statement.beginning_balance != null ? formatCurrency(Number(statement.beginning_balance), currency) : "—"}
            icon={Wallet}
          />
          <StatCard
            label="Closing Balance"
            value={statement.ending_balance != null ? formatCurrency(Number(statement.ending_balance), currency) : "—"}
            icon={Landmark}
          />
          <StatCard label="Total Debits" value={formatCurrency(totalDebits, currency)} icon={ArrowDownCircle} subtext="Money out" />
          <StatCard label="Total Credits" value={formatCurrency(totalCredits, currency)} icon={ArrowUpCircle} subtext="Money in" />
          <StatCard label="Net Movement" value={formatCurrency(net, currency)} icon={Scale} subtext={net < 0 ? "Outflow month" : "Inflow month"} />
          <StatCard label="Transactions" value={transactions.length} icon={ReceiptText} subtext={`${statement.page_count} pages`} />
        </div>

        {/* Daily balance trend */}
        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="font-semibold text-foreground text-sm mb-1">Daily Closing Balance</h2>
            <p className="text-xs text-muted-foreground mb-3">
              From the statement&apos;s per-day closing balance rows.
            </p>
            <BalanceTrendChart balances={statement.daily_balances} currency={currency} />
          </CardContent>
        </Card>

        {/* Breakdown by transaction type */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm">Breakdown by Transaction Type</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Where the money went — trade bills, check clearing, charges and interest at a glance.
            </p>
          </div>
          <CardContent className="p-4 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Count</TableHead>
                  <TableHead className="text-right">Debits</TableHead>
                  <TableHead className="text-right">Credits</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {categories.map(([category, row]) => (
                  <TableRow key={category}>
                    <TableCell className="text-sm">{category}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.count}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.debit > 0 ? formatCurrency(row.debit, currency) : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.credit > 0 ? formatCurrency(row.credit, currency) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Transactions */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm">
              Transactions ({transactions.length})
            </h3>
          </div>
          <CardContent className="p-4">
            <TableControls
              search={table.search}
              onSearch={table.setSearch}
              sort={table.sort}
              onSort={table.setSort}
              sortOptions={TXN_SORTS}
              placeholder="Search by type, reference or detail…"
            />
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Reference</TableHead>
                    <TableHead>Detail</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {table.visible.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="text-xs whitespace-nowrap">{formatDate(t.txn_date)}</TableCell>
                      <TableCell className="text-sm">{t.category ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{t.reference ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-md truncate">{t.detail ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {t.debit != null ? formatCurrency(Number(t.debit), currency) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm text-emerald-700">
                        {t.credit != null ? formatCurrency(Number(t.credit), currency) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination
              page={table.page}
              totalPages={table.totalPages}
              total={table.total}
              pageSize={table.pageSize}
              onChange={table.setPage}
            />
          </CardContent>
        </Card>
      </main>
    </RoleGuard>
  );
}

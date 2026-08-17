"use client";

// Banking module (Aug 2026) — super-admin only for now. Upload Citi-style
// statement PDFs; the AI vision provider extracts them server-side, and the
// dashboard reads the stored rows. Standalone from Advance Payment.

import { useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Landmark, Loader2, Trash2, Upload } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { TableControls } from "@/components/ui/TableControls";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  useBankStatements,
  useDeleteBankStatement,
  useUploadBankStatement,
} from "@/hooks/useBankStatements";
import { byString, useClientTable } from "@/hooks/useClientTable";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { BankStatement } from "@/types";

function StatusPill({ status }: { status: BankStatement["status"] }) {
  if (status === "processing") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
        <Loader2 className="h-3 w-3 animate-spin" /> Processing
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
        Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
      Extracted
    </span>
  );
}

const STATEMENT_SORTS = [
  { value: "period", label: "Period (newest first)", compare: byString<BankStatement>((s) => s.period_start ?? "", true) },
  { value: "uploaded", label: "Uploaded (newest first)", compare: byString<BankStatement>((s) => s.created_at, true) },
  { value: "bank", label: "Bank (A–Z)", compare: byString<BankStatement>((s) => s.bank_name) },
];

export default function BankStatementsPage() {
  const { data: statements = [], isLoading } = useBankStatements();
  const uploadStatement = useUploadBankStatement();
  const deleteStatement = useDeleteBankStatement();
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BankStatement | null>(null);

  const table = useClientTable(statements, {
    searchHaystack: (s) => [
      s.bank_name, s.account_number, s.currency, s.original_filename, s.status,
    ],
    sortOptions: STATEMENT_SORTS,
    pageSize: 20,
  });

  // One-click upload: the button opens the picker; the chosen PDF uploads
  // immediately (same pattern as the tranche TT copy upload).
  const doUpload = async (file: File) => {
    if (file.size > 15 * 1024 * 1024) {
      toast.error("The PDF must be 15 MB or smaller.");
      return;
    }
    try {
      await uploadStatement.mutateAsync(file);
      toast.success(
        "Statement uploaded — extraction is running in the background. " +
        "The row will flip to Extracted when it finishes.",
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const doDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteStatement.mutateAsync(deleteTarget.id);
      toast.success("Statement deleted.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to delete the statement.");
    } finally {
      setDeleteTarget(null);
    }
  };

  const extracted = statements.filter((s) => s.status === "extracted");

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav
        title="Bank Statements"
        subtitle="Upload monthly statements — transactions are extracted automatically and analysed below"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        {/* Upload */}
        <Card>
          <CardContent className="p-5 md:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold text-foreground text-sm flex items-center gap-2">
                <Landmark className="h-4 w-4" /> Upload a statement PDF
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Citi Asia Account Statement layout supported. Pages are read by the
                configured AI provider; an integrity check compares the extracted
                totals against the statement&apos;s own ending balance.
              </p>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void doUpload(file);
              }}
            />
            <Button
              onClick={() => fileInput.current?.click()}
              disabled={uploadStatement.isPending}
              className="gap-2 shrink-0"
            >
              <Upload className="h-4 w-4" />
              {uploadStatement.isPending ? "Uploading…" : "Upload Statement"}
            </Button>
          </CardContent>
        </Card>

        {/* Statements list */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm">Statements</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Click an extracted statement to open its dashboard.
            </p>
          </div>
          <CardContent className="p-4">
            {isLoading ? (
              <Table><TableBody><TableSkeleton rows={4} cols={8} /></TableBody></Table>
            ) : statements.length === 0 ? (
              <EmptyState
                icon={Landmark}
                title="No statements yet"
                description="Upload your first bank statement PDF above."
              />
            ) : (
              <>
                <TableControls
                  search={table.search}
                  onSearch={table.setSearch}
                  sort={table.sort}
                  onSort={table.setSort}
                  sortOptions={STATEMENT_SORTS}
                  placeholder="Search by bank, account, currency or file…"
                />
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Bank</TableHead>
                        <TableHead>Account</TableHead>
                        <TableHead>Period</TableHead>
                        <TableHead>Currency</TableHead>
                        <TableHead className="text-right">Opening</TableHead>
                        <TableHead className="text-right">Closing</TableHead>
                        <TableHead className="text-right">Net Movement</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {table.visible.map((s) => {
                        const net =
                          s.beginning_balance != null && s.ending_balance != null
                            ? Number(s.ending_balance) - Number(s.beginning_balance)
                            : null;
                        return (
                          <TableRow key={s.id}>
                            <TableCell className="font-medium text-sm">{s.bank_name}</TableCell>
                            <TableCell className="font-mono text-xs text-muted-foreground">
                              {s.account_number ?? "—"}
                            </TableCell>
                            <TableCell className="text-xs whitespace-nowrap">
                              {s.period_start ? `${formatDate(s.period_start)} – ${formatDate(s.period_end)}` : s.original_filename}
                            </TableCell>
                            <TableCell className="text-xs">{s.currency ?? "—"}</TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                              {s.beginning_balance != null ? formatCurrency(Number(s.beginning_balance), s.currency) : "—"}
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                              {s.ending_balance != null ? formatCurrency(Number(s.ending_balance), s.currency) : "—"}
                            </TableCell>
                            <TableCell className={`text-right tabular-nums text-sm font-semibold ${net != null && net < 0 ? "text-red-700" : "text-emerald-700"}`}>
                              {net != null ? formatCurrency(net, s.currency) : "—"}
                            </TableCell>
                            <TableCell><StatusPill status={s.status} /></TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1.5 whitespace-nowrap">
                                {s.status === "extracted" && (
                                  <Button size="sm" variant="outline" asChild>
                                    <Link href={`/bank/${s.id}`}>Open</Link>
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  aria-label="Delete statement"
                                  className="text-muted-foreground hover:text-destructive"
                                  onClick={() => setDeleteTarget(s)}
                                  disabled={deleteStatement.isPending}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
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
              </>
            )}
          </CardContent>
        </Card>

        {/* Month-over-month comparison across extracted statements */}
        {extracted.length > 1 && (
          <Card className="overflow-hidden">
            <div className="px-5 py-4 border-b border-border">
              <h3 className="font-semibold text-foreground text-sm">Month-over-Month</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Opening, closing and net movement across uploaded statements (per account).
              </p>
            </div>
            <CardContent className="p-4 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Period</TableHead>
                    <TableHead>Account</TableHead>
                    <TableHead className="text-right">Opening</TableHead>
                    <TableHead className="text-right">Closing</TableHead>
                    <TableHead className="text-right">Net Movement</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...extracted]
                    .sort((a, b) => (a.period_start ?? "").localeCompare(b.period_start ?? ""))
                    .map((s) => {
                      const net =
                        s.beginning_balance != null && s.ending_balance != null
                          ? Number(s.ending_balance) - Number(s.beginning_balance)
                          : null;
                      return (
                        <TableRow key={s.id}>
                          <TableCell className="text-xs whitespace-nowrap">
                            {s.period_start ? `${formatDate(s.period_start)} – ${formatDate(s.period_end)}` : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{s.account_number ?? "—"} {s.currency ? `(${s.currency})` : ""}</TableCell>
                          <TableCell className="text-right tabular-nums text-sm">
                            {s.beginning_balance != null ? formatCurrency(Number(s.beginning_balance), s.currency) : "—"}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-sm">
                            {s.ending_balance != null ? formatCurrency(Number(s.ending_balance), s.currency) : "—"}
                          </TableCell>
                          <TableCell className={`text-right tabular-nums text-sm font-semibold ${net != null && net < 0 ? "text-red-700" : "text-emerald-700"}`}>
                            {net != null ? formatCurrency(net, s.currency) : "—"}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </main>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete this statement?"
        description="The statement and all its extracted transactions will be removed. Upload the PDF again to re-extract."
        confirmLabel="Yes, delete"
        onConfirm={doDelete}
      />
    </RoleGuard>
  );
}

"use client";

// File Remarks module (CIO batch 2, Aug 2026; reworked 4 Aug) — a tracked
// channel from merchandisers to Accounts that bypasses Adjust Invoices for
// the time being. Two categories only:
//   Split Invoices        — file splits to N × (new file no. + amount)
//   Invoice amount changes — old file + amount → new file + amount
// Only payment-completed files are eligible; the remark text is optional.
// Moves no money. UAT Aug 2026 (item 14): Accounts see a decision queue of
// remark SUMMARIES (not the merchandiser form) with Processed/Approve and
// Reject buttons — the merchandiser is notified of either outcome.

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Check, Inbox, MessageSquarePlus, Plus, Trash2, X } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Label } from "@/components/ui/label";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Pagination } from "@/components/ui/Pagination";
import { TableControls } from "@/components/ui/TableControls";
import { byString, useClientTable } from "@/hooks/useClientTable";
import { useAuth } from "@/hooks/useAuth";
import { useRequests } from "@/hooks/useRequests";
import {
  useCreateFileRemark,
  useDecideFileRemark,
  useFileRemarks,
} from "@/hooks/useFileRemarks";
import { formatDate } from "@/lib/utils";
import type { FileRemark, FileRemarkCategory } from "@/types";

const CATEGORY_LABELS: Record<FileRemarkCategory, string> = {
  invoice_split: "Split Invoices",
  // Renamed from "Invoice amount changes" (11 Aug 2026).
  invoice_amount_change: "Invoice Change",
};

type SplitRow = { file_number: string; amount: string };

const STATUS_PILLS: Record<FileRemark["status"], { label: string; cls: string }> = {
  open:     { label: "Open",     cls: "text-amber-700 bg-amber-50 border-amber-200" },
  approved: { label: "Approved", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  rejected: { label: "Rejected", cls: "text-red-700 bg-red-50 border-red-200" },
  resolved: { label: "Resolved", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
};

function StatusPill({ status }: { status: FileRemark["status"] }) {
  const pill = STATUS_PILLS[status] ?? STATUS_PILLS.open;
  return (
    <span className={`inline-flex items-center text-xs font-medium border px-2 py-0.5 rounded-full ${pill.cls}`}>
      {pill.label}
    </span>
  );
}

// Approve = mark processed (optional note); Reject = mandatory reason.
function DecideDialog({
  remark,
  decision,
  onClose,
  onConfirm,
  busy,
}: {
  remark: FileRemark | null;
  decision: "approved" | "rejected";
  onClose: () => void;
  onConfirm: (note: string) => void;
  busy: boolean;
}) {
  const [note, setNote] = useState("");
  if (!remark) return null;
  const rejecting = decision === "rejected";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-card rounded-xl border border-border shadow-lg p-6 w-full max-w-md space-y-4">
        <h3 className="font-semibold text-foreground">
          {rejecting ? "Reject File Remark" : "Approve File Remark"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {CATEGORY_LABELS[remark.category]} on {remark.request_number} — the
          merchandiser will be notified.{" "}
          {rejecting ? "A reason is mandatory." : "The note is optional."}
        </p>
        <Textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={rejecting ? "Reason for rejection (required)" : "Response to the merchandiser (optional)"}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => { setNote(""); onClose(); }} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant={rejecting ? "destructive" : "default"}
            disabled={busy || (rejecting && !note.trim())}
            onClick={() => { onConfirm(note.trim()); setNote(""); }}
          >
            {busy ? "Saving…" : rejecting ? "Confirm Reject" : "Processed / Approve"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Structured details cell — split targets or old→new amounts. Splits show
// the PARENT file first (10 Aug rework: "from which file to which files") —
// older rows without a stored parent fall back to the request number.
function RemarkDetails({ r }: { r: FileRemark }) {
  if (r.category === "invoice_split" && r.split_targets?.length) {
    // Prefer the parent's CURRENT sunshine invoice number — falls back to
    // the stored parent reference, then the request number (legacy rows).
    const parent = r.sunshine_invoice_number ?? r.old_file_number ?? r.request_number ?? "—";
    // Balance left on the original file after the split (19 Aug 2026) —
    // shown even at 0.00 as explicit confirmation of a full allocation.
    // Needs the stored old amount (legacy rows without one show no balance).
    const splitTotal = r.split_targets.reduce((sum, t) => sum + Number(t.amount), 0);
    const balance = r.old_amount != null ? Number(r.old_amount) - splitTotal : null;
    return (
      <div className="text-xs text-muted-foreground space-y-0.5">
        <p className="font-medium text-foreground">
          From {parent}
          {r.old_amount != null
            ? ` (${Number(r.old_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })})`
            : ""}
        </p>
        {r.split_targets.map((t, i) => (
          <p key={`${t.file_number}-${i}`}>
            → {t.file_number} · {Number(t.amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        ))}
        {balance != null && (
          <p className={balance < 0 ? "text-destructive font-medium" : "font-medium text-foreground"}>
            Balance on {parent}:{" "}
            {balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        )}
      </div>
    );
  }
  // Invoice Change: explicit From → To wording (11 Aug) — the file number
  // changes from the parent file to the new one.
  const fromFile = r.old_file_number ?? r.sunshine_invoice_number ?? r.request_number;
  return (
    <div className="text-xs text-muted-foreground space-y-0.5">
      {fromFile && (
        <p>
          <span className="font-medium text-foreground">From</span> {fromFile}
          {r.old_amount != null
            ? ` (${Number(r.old_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })})`
            : ""}
        </p>
      )}
      {r.new_file_number && (
        <p>
          <span className="font-medium text-foreground">To</span> {r.new_file_number}
          {r.new_amount != null
            ? ` (${Number(r.new_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })})`
            : ""}
        </p>
      )}
    </div>
  );
}

export default function FileRemarksPage() {
  const { user } = useAuth();
  const isDecider = user?.role === "accounts_team" || user?.role === "super_admin";
  // UAT Aug 2026 item 14 + 10 Aug refinement: ONLY merchandisers see the New
  // File Remark form — every decider role sees just open remarks + history.
  const canRaise = user?.role === "merchandiser";

  // Role-scoped server-side; only payment-completed files are eligible.
  const { data: requests = [] } = useRequests();
  const completedRequests = requests.filter((r) => r.current_status === "payment_processed");
  const { data: remarks = [], isLoading } = useFileRemarks();
  const createRemark = useCreateFileRemark();
  const decideRemark = useDecideFileRemark();

  // Category comes FIRST (4 Aug rework) and drives the rest of the form.
  const [category, setCategory] = useState<FileRemarkCategory>("invoice_split");
  const [requestId, setRequestId] = useState("");
  const [splitRows, setSplitRows] = useState<SplitRow[]>([{ file_number: "", amount: "" }]);
  const [newFile, setNewFile] = useState("");
  const [remarkText, setRemarkText] = useState("");
  const [decideTarget, setDecideTarget] = useState<FileRemark | null>(null);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");

  const openRemarks = remarks.filter((r) => r.status === "open");

  // Request # cells link to the request's own form (19 Aug 2026) — the
  // merchandiser's request view for merchandisers, the payment-queue view
  // for accounts / finance / super admin (its RoleGuard admits all three).
  const requestHref = (r: FileRemark) =>
    user?.role === "merchandiser"
      ? `/merchandiser/${r.deposit_request_id}`
      : `/accounts/${r.deposit_request_id}`;
  const RequestLink = ({ r }: { r: FileRemark }) =>
    r.request_number ? (
      <Link
        href={requestHref(r)}
        className="text-primary hover:underline underline-offset-2"
      >
        {r.request_number}
      </Link>
    ) : (
      <>—</>
    );

  // Search / sort / pagination (10 Aug 2026, app-wide table controls).
  const remarkHaystack = (r: FileRemark) => [
    r.request_number, CATEGORY_LABELS[r.category], r.old_file_number,
    r.new_file_number, r.created_by_name, r.remark, r.status,
    ...(r.split_targets?.map((t) => t.file_number) ?? []),
  ];
  const remarkSorts = [
    { value: "newest", label: "Newest first", compare: byString<FileRemark>((r) => r.created_at, true) },
    { value: "oldest", label: "Oldest first", compare: byString<FileRemark>((r) => r.created_at) },
    { value: "request", label: "Request #", compare: byString<FileRemark>((r) => r.request_number ?? "") },
  ];
  const openTable = useClientTable(openRemarks, {
    searchHaystack: remarkHaystack, sortOptions: remarkSorts, pageSize: 20,
  });
  const historyTable = useClientTable(remarks, {
    searchHaystack: remarkHaystack, sortOptions: remarkSorts, pageSize: 20,
  });

  // The old amount pre-populates from the selected file's deposit amount and
  // is NOT editable (4 Aug follow-up) — the server derives it independently.
  const selectedRequest = completedRequests.find((r) => r.id === requestId);
  const oldAmountDisplay =
    selectedRequest != null ? Number(selectedRequest.deposit_amount).toFixed(2) : "";

  // Amounts can never exceed the file's deposit ("old") amount (7 Aug fix).
  const depositCeiling = selectedRequest != null ? Number(selectedRequest.deposit_amount) : null;
  const splitTotal = splitRows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const splitOverCeiling = depositCeiling != null && splitTotal > depositCeiling;
  // Live balance left on the original file as split amounts are typed
  // (19 Aug 2026) — matches the balance shown on submitted remarks.
  const splitBalance = depositCeiling != null ? depositCeiling - splitTotal : null;

  const splitRowsValid =
    splitRows.length > 0 &&
    splitRows.every((row) => row.file_number.trim() && Number(row.amount) > 0) &&
    !splitOverCeiling;
  // Invoice Change (19 Aug 2026): the whole invoice changes number, not
  // value — the amount is pre-filled from the file and locked; the server
  // derives it independently, so only the new file number is client input.
  const amountChangeValid = Boolean(newFile.trim());
  const canSubmit =
    !!requestId && (category === "invoice_split" ? splitRowsValid : amountChangeValid);

  const resetForm = () => {
    setRequestId("");
    setSplitRows([{ file_number: "", amount: "" }]);
    setNewFile("");
    setRemarkText("");
  };

  const doCreate = async () => {
    if (!canSubmit) return;
    try {
      await createRemark.mutateAsync({
        deposit_request_id: requestId,
        category,
        // The old amount is deliberately NOT sent — the server derives it
        // from the selected file's deposit amount.
        ...(category === "invoice_split"
          ? {
              split_targets: splitRows.map((row) => ({
                file_number: row.file_number.trim(),
                amount: Number(row.amount),
              })),
            }
          : {
              // The old file reference (10 Aug rework) AND the new amount
              // (19 Aug: whole-invoice change keeps the amount) are both
              // server-derived — only the new file number is typed.
              new_file_number: newFile.trim(),
            }),
        remark: remarkText.trim() || undefined,
      });
      toast.success("File remark raised — the Accounts team has been notified.");
      resetForm();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to raise the file remark.");
    }
  };

  const doDecide = async (note: string) => {
    if (!decideTarget) return;
    try {
      await decideRemark.mutateAsync({
        id: decideTarget.id,
        decision,
        responseNote: note || undefined,
      });
      toast.success(
        decision === "approved"
          ? "Remark approved — the merchandiser has been notified."
          : "Remark rejected — the merchandiser has been notified.",
      );
      setDecideTarget(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save the decision.");
    }
  };

  const inputCls =
    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <RoleGuard allowedRoles={["merchandiser", "accounts_team", "super_admin", "finance_admin"]}>
      <TopNav
        title="File Remarks"
        subtitle="Invoice splits and amount changes on payment-completed files — routed to Accounts, no balances move"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-5xl mx-auto w-full">
        {canRaise && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-4">
              <div className="flex items-center gap-2">
                <MessageSquarePlus className="h-4 w-4 text-muted-foreground" />
                <h2 className="font-semibold text-foreground text-sm">New File Remark</h2>
              </div>
              <p className="text-xs text-muted-foreground -mt-2">
                Only files whose payment is completed can be selected. The Accounts
                team is notified and approves or rejects the remark once actioned.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="fr-category">Category</Label>
                  <select
                    id="fr-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value as FileRemarkCategory)}
                    className={`mt-1 ${inputCls}`}
                  >
                    <option value="invoice_split">Split Invoices</option>
                    <option value="invoice_amount_change">Invoice Change</option>
                  </select>
                </div>
                <div>
                  <Label htmlFor="fr-request">Select file (payment completed)</Label>
                  <select
                    id="fr-request"
                    value={requestId}
                    onChange={(e) => setRequestId(e.target.value)}
                    className={`mt-1 ${inputCls}`}
                  >
                    <option value="">
                      {completedRequests.length === 0
                        ? "No payment-completed files"
                        : "Select file"}
                    </option>
                    {completedRequests.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.request_number}
                        {r.sunshine_invoice_number ? ` (${r.sunshine_invoice_number})` : ""} — {r.supplier.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {category === "invoice_split" ? (
                <div className="space-y-2">
                  <div className="sm:max-w-64">
                    <Label htmlFor="fr-split-old-amount">Old file amount</Label>
                    <input
                      id="fr-split-old-amount"
                      type="text"
                      value={oldAmountDisplay}
                      readOnly
                      disabled
                      placeholder="Select a file above"
                      className={`mt-1 ${inputCls} bg-muted opacity-70 cursor-not-allowed`}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Pre-filled from the selected file — not editable.
                    </p>
                  </div>
                  <Label>
                    File splits to<span className="ml-0.5" aria-hidden="true">*</span>
                  </Label>
                  {splitRows.map((row, i) => (
                    <div key={i} className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="text"
                        placeholder={`New file no. ${i + 1}`}
                        value={row.file_number}
                        onChange={(e) =>
                          setSplitRows((rows) =>
                            rows.map((r, j) => (j === i ? { ...r, file_number: e.target.value } : r)),
                          )
                        }
                        className={inputCls}
                      />
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="Amount"
                        value={row.amount}
                        onChange={(e) =>
                          setSplitRows((rows) =>
                            rows.map((r, j) => (j === i ? { ...r, amount: e.target.value } : r)),
                          )
                        }
                        className={`${inputCls} sm:max-w-44`}
                      />
                      {splitRows.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setSplitRows((rows) => rows.filter((_, j) => j !== i))}
                          aria-label={`Remove split row ${i + 1}`}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-muted transition-colors self-center"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setSplitRows((rows) => [...rows, { file_number: "", amount: "" }])}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1.5" /> Add file
                    </Button>
                    {depositCeiling != null && (
                      <p className={`text-xs ${splitOverCeiling ? "text-destructive" : "text-muted-foreground"}`}>
                        Split total: {splitTotal.toFixed(2)} of {depositCeiling.toFixed(2)}
                        {splitBalance != null && (
                          <span className={splitOverCeiling ? "" : "font-medium text-foreground"}>
                            {" "}· Balance left: {splitBalance.toFixed(2)}
                          </span>
                        )}
                      </p>
                    )}
                  </div>
                  {splitOverCeiling && (
                    <p className="text-xs text-destructive">
                      The split amounts cannot exceed the file&apos;s old amount of{" "}
                      {depositCeiling!.toFixed(2)}.
                    </p>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* The old file reference is the selected file itself —
                      server-derived, nothing to type (10 Aug rework). */}
                  <div>
                    <Label htmlFor="fr-old-amount">Old file amount</Label>
                    <input
                      id="fr-old-amount"
                      type="text"
                      value={oldAmountDisplay}
                      readOnly
                      disabled
                      placeholder="Select a file above"
                      className={`mt-1 ${inputCls} bg-muted opacity-70 cursor-not-allowed`}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Pre-filled from the selected file — not editable.
                    </p>
                  </div>
                  <div>
                    <Label htmlFor="fr-new-file">
                      New file number<span className="ml-0.5" aria-hidden="true">*</span>
                    </Label>
                    <input
                      id="fr-new-file"
                      type="text"
                      value={newFile}
                      onChange={(e) => setNewFile(e.target.value)}
                      className={`mt-1 ${inputCls}`}
                    />
                  </div>
                  <div>
                    <Label htmlFor="fr-new-amount">New file amount</Label>
                    {/* 19 Aug 2026: the whole invoice changes number, not
                        value — pre-filled from the file and locked; the
                        server derives it independently. */}
                    <input
                      id="fr-new-amount"
                      type="text"
                      value={oldAmountDisplay}
                      readOnly
                      disabled
                      placeholder="Select a file above"
                      className={`mt-1 ${inputCls} bg-muted opacity-70 cursor-not-allowed`}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Same as the old amount — a whole-invoice change keeps the value.
                    </p>
                  </div>
                </div>
              )}

              <div>
                <Label htmlFor="fr-remark">Remarks (optional)</Label>
                <Textarea
                  id="fr-remark"
                  rows={2}
                  className="mt-1"
                  value={remarkText}
                  onChange={(e) => setRemarkText(e.target.value)}
                  placeholder="Any additional context for the Accounts team."
                />
              </div>

              <Button onClick={doCreate} disabled={!canSubmit || createRemark.isPending}>
                {createRemark.isPending ? "Submitting…" : "Raise File Remark"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Accounts inbox — open remarks awaiting action */}
        {(isDecider || user?.role === "finance_admin") && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <div className="flex items-center gap-2 mb-1">
                <Inbox className="h-4 w-4 text-muted-foreground" />
                <h2 className="font-semibold text-foreground text-sm">
                  Open Remarks{openRemarks.length > 0 ? ` (${openRemarks.length})` : ""}
                </h2>
              </div>
              <p className="text-xs text-muted-foreground mb-4">
                Summary of each requested change — action it manually, then mark it
                Processed/Approve or Reject. The merchandiser is notified either way.
              </p>
              {isLoading ? (
                <Table><TableBody><TableSkeleton rows={2} cols={6} /></TableBody></Table>
              ) : openRemarks.length === 0 ? (
                <EmptyState
                  icon={Inbox}
                  title="No open file remarks"
                  description="Merchandiser-raised remarks awaiting action will appear here."
                />
              ) : (
                <div className="overflow-x-auto">
                  <TableControls
                    search={openTable.search}
                    onSearch={openTable.setSearch}
                    sort={openTable.sort}
                    onSort={openTable.setSort}
                    sortOptions={remarkSorts}
                    placeholder="Search by request #, file no., category or raiser…"
                  />
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Raised</TableHead>
                        <TableHead>Request #</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Details</TableHead>
                        <TableHead>Remark / By</TableHead>
                        {isDecider && <TableHead />}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {openTable.visible.map((r) => (
                        <TableRow key={r.id}>
                          <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                            {formatDate(r.created_at)}
                          </TableCell>
                          <TableCell className="font-mono text-xs font-semibold whitespace-nowrap">
                            <RequestLink r={r} />
                          </TableCell>
                          <TableCell className="text-sm whitespace-nowrap">
                            {CATEGORY_LABELS[r.category]}
                          </TableCell>
                          <TableCell><RemarkDetails r={r} /></TableCell>
                          <TableCell className="text-sm max-w-64">
                            {r.remark ?? "—"}
                            <span className="text-xs text-muted-foreground"> — {r.created_by_name ?? "?"}</span>
                          </TableCell>
                          {isDecider && (
                            <TableCell>
                              <div className="flex gap-2 whitespace-nowrap">
                                <Button
                                  size="sm"
                                  onClick={() => { setDecision("approved"); setDecideTarget(r); }}
                                  disabled={decideRemark.isPending}
                                  className="gap-1"
                                >
                                  <Check className="h-3.5 w-3.5" /> Processed / Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() => { setDecision("rejected"); setDecideTarget(r); }}
                                  disabled={decideRemark.isPending}
                                  className="gap-1"
                                >
                                  <X className="h-3.5 w-3.5" /> Reject
                                </Button>
                              </div>
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination
                    page={openTable.page}
                    totalPages={openTable.totalPages}
                    total={openTable.total}
                    pageSize={openTable.pageSize}
                    onChange={openTable.setPage}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* History — own remarks for merchandisers, everything for Accounts */}
        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="font-semibold text-foreground text-sm mb-4">Remark History</h2>
            {isLoading ? (
              <Table><TableBody><TableSkeleton rows={4} cols={6} /></TableBody></Table>
            ) : remarks.length === 0 ? (
              <EmptyState
                icon={MessageSquarePlus}
                title="No file remarks yet"
                description="Raised remarks and their decisions will appear here."
              />
            ) : (
              <div className="overflow-x-auto">
                <TableControls
                  search={historyTable.search}
                  onSearch={historyTable.setSearch}
                  sort={historyTable.sort}
                  onSort={historyTable.setSort}
                  sortOptions={remarkSorts}
                  placeholder="Search by request #, file no., category or status…"
                />
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Raised</TableHead>
                      <TableHead>Request #</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Details</TableHead>
                      <TableHead>Remark</TableHead>
                      <TableHead>Status / Response</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {historyTable.visible.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(r.created_at)}
                        </TableCell>
                        <TableCell className="font-mono text-xs font-semibold whitespace-nowrap">
                          <RequestLink r={r} />
                        </TableCell>
                        <TableCell className="text-sm whitespace-nowrap">
                          {CATEGORY_LABELS[r.category]}
                        </TableCell>
                        <TableCell><RemarkDetails r={r} /></TableCell>
                        <TableCell className="text-sm max-w-64">{r.remark ?? "—"}</TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <StatusPill status={r.status} />
                            {r.response_note && (
                              <p className="text-xs text-muted-foreground max-w-56">
                                {r.response_note}
                              </p>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Pagination
                  page={historyTable.page}
                  totalPages={historyTable.totalPages}
                  total={historyTable.total}
                  pageSize={historyTable.pageSize}
                  onChange={historyTable.setPage}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      <DecideDialog
        remark={decideTarget}
        decision={decision}
        onClose={() => setDecideTarget(null)}
        onConfirm={doDecide}
        busy={decideRemark.isPending}
      />
    </RoleGuard>
  );
}

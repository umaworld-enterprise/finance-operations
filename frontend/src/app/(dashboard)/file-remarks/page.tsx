"use client";

// File Remarks module (CIO batch 2, Aug 2026) — a tracked Open → Resolved
// channel from merchandisers to Accounts that bypasses Adjust Invoices for
// the time being: invoice-number changes and invoice splits on files
// (including paid & processed ones) are raised as structured remarks.
// Moves no money — Accounts act manually and resolve with an optional note.

import { useState } from "react";
import { toast } from "sonner";
import { Inbox, MessageSquarePlus } from "lucide-react";
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
import { useAuth } from "@/hooks/useAuth";
import { useRequests } from "@/hooks/useRequests";
import {
  useCreateFileRemark,
  useFileRemarks,
  useResolveFileRemark,
} from "@/hooks/useFileRemarks";
import { formatDate } from "@/lib/utils";
import type { FileRemark, FileRemarkCategory } from "@/types";

const CATEGORIES: {
  value: FileRemarkCategory;
  label: string;
  needsOld: boolean;
  needsNew: boolean;
  newLabel: string;
}[] = [
  {
    value: "invoice_number_change",
    label: "Invoice number change",
    needsOld: true,
    needsNew: true,
    newLabel: "New file number",
  },
  {
    value: "invoice_split",
    label: "Invoice split",
    needsOld: false,
    needsNew: true,
    newLabel: "Splits to (file number/s)",
  },
  { value: "other", label: "Other", needsOld: false, needsNew: false, newLabel: "" },
];

const CATEGORY_LABELS: Record<FileRemarkCategory, string> = {
  invoice_number_change: "Invoice number change",
  invoice_split: "Invoice split",
  other: "Other",
};

function StatusPill({ status }: { status: FileRemark["status"] }) {
  return status === "resolved" ? (
    <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
      Resolved
    </span>
  ) : (
    <span className="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
      Open
    </span>
  );
}

function ResolveDialog({
  remark,
  onClose,
  onConfirm,
  busy,
}: {
  remark: FileRemark | null;
  onClose: () => void;
  onConfirm: (note: string) => void;
  busy: boolean;
}) {
  const [note, setNote] = useState("");
  if (!remark) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-card rounded-xl border border-border shadow-lg p-6 w-full max-w-md space-y-4">
        <h3 className="font-semibold text-foreground">Resolve File Remark</h3>
        <p className="text-sm text-muted-foreground">
          {CATEGORY_LABELS[remark.category]} on {remark.request_number} — the
          merchandiser will be notified. The response note is optional.
        </p>
        <Textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Response to the merchandiser (optional)"
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => { setNote(""); onClose(); }} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" disabled={busy} onClick={() => { onConfirm(note.trim()); setNote(""); }}>
            {busy ? "Resolving…" : "Mark Resolved"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function RemarkFileNumbers({ r }: { r: FileRemark }) {
  return (
    <span className="text-xs text-muted-foreground">
      {r.old_file_number ? `old: ${r.old_file_number}` : ""}
      {r.old_file_number && r.new_file_number ? " → " : ""}
      {r.new_file_number ? `new: ${r.new_file_number}` : ""}
    </span>
  );
}

export default function FileRemarksPage() {
  const { user } = useAuth();
  const isDecider = user?.role === "accounts_team" || user?.role === "super_admin";
  const canRaise = isDecider || user?.role === "merchandiser";

  // Role-scoped server-side: merchandisers get their own requests.
  const { data: requests = [] } = useRequests();
  const { data: remarks = [], isLoading } = useFileRemarks();
  const createRemark = useCreateFileRemark();
  const resolveRemark = useResolveFileRemark();

  const [requestId, setRequestId] = useState("");
  const [category, setCategory] = useState<FileRemarkCategory>("invoice_number_change");
  const [oldFile, setOldFile] = useState("");
  const [newFile, setNewFile] = useState("");
  const [remarkText, setRemarkText] = useState("");
  const [resolveTarget, setResolveTarget] = useState<FileRemark | null>(null);

  const cat = CATEGORIES.find((c) => c.value === category)!;
  const openRemarks = remarks.filter((r) => r.status === "open");

  const canSubmit =
    requestId &&
    remarkText.trim() &&
    (!cat.needsOld || oldFile.trim()) &&
    (!cat.needsNew || newFile.trim());

  const doCreate = async () => {
    if (!canSubmit) return;
    try {
      await createRemark.mutateAsync({
        deposit_request_id: requestId,
        category,
        old_file_number: cat.needsOld ? oldFile.trim() : undefined,
        new_file_number: cat.needsNew ? newFile.trim() : undefined,
        remark: remarkText.trim(),
      });
      toast.success("File remark raised — the Accounts team has been notified.");
      setRequestId("");
      setOldFile("");
      setNewFile("");
      setRemarkText("");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to raise the file remark.");
    }
  };

  const doResolve = async (note: string) => {
    if (!resolveTarget) return;
    try {
      await resolveRemark.mutateAsync({ id: resolveTarget.id, responseNote: note || undefined });
      toast.success("Remark resolved — the merchandiser has been notified.");
      setResolveTarget(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to resolve the remark.");
    }
  };

  const selectCls =
    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <RoleGuard allowedRoles={["merchandiser", "accounts_team", "super_admin", "finance_admin"]}>
      <TopNav
        title="File Remarks"
        subtitle="Invoice number changes and splits on existing files — routed to Accounts, no balances move"
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
                Works on any of your files, including paid &amp; processed ones. The
                Accounts team is notified and resolves the remark once actioned.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="fr-request">File / Request</Label>
                  <select
                    id="fr-request"
                    value={requestId}
                    onChange={(e) => setRequestId(e.target.value)}
                    className={`mt-1 ${selectCls}`}
                  >
                    <option value="">Select request</option>
                    {requests.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.request_number}
                        {r.sunshine_invoice_number ? ` (${r.sunshine_invoice_number})` : ""} — {r.supplier.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="fr-category">Category</Label>
                  <select
                    id="fr-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value as FileRemarkCategory)}
                    className={`mt-1 ${selectCls}`}
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>
                {cat.needsOld && (
                  <div>
                    <Label htmlFor="fr-old">
                      Old file number<span className="ml-0.5" aria-hidden="true">*</span>
                    </Label>
                    <input
                      id="fr-old"
                      type="text"
                      value={oldFile}
                      onChange={(e) => setOldFile(e.target.value)}
                      className={`mt-1 ${selectCls}`}
                    />
                  </div>
                )}
                {cat.needsNew && (
                  <div>
                    <Label htmlFor="fr-new">
                      {cat.newLabel}<span className="ml-0.5" aria-hidden="true">*</span>
                    </Label>
                    <input
                      id="fr-new"
                      type="text"
                      value={newFile}
                      onChange={(e) => setNewFile(e.target.value)}
                      className={`mt-1 ${selectCls}`}
                    />
                  </div>
                )}
                <div className="sm:col-span-2">
                  <Label htmlFor="fr-remark">
                    Remarks<span className="ml-0.5" aria-hidden="true">*</span>
                  </Label>
                  <Textarea
                    id="fr-remark"
                    rows={2}
                    className="mt-1"
                    value={remarkText}
                    onChange={(e) => setRemarkText(e.target.value)}
                    placeholder="e.g. Full deposit amount is transferred to the new file."
                  />
                </div>
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
              <div className="flex items-center gap-2 mb-4">
                <Inbox className="h-4 w-4 text-muted-foreground" />
                <h2 className="font-semibold text-foreground text-sm">
                  Open Remarks{openRemarks.length > 0 ? ` (${openRemarks.length})` : ""}
                </h2>
              </div>
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
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Raised</TableHead>
                        <TableHead>Request #</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>File numbers</TableHead>
                        <TableHead>Remark / By</TableHead>
                        {isDecider && <TableHead />}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {openRemarks.map((r) => (
                        <TableRow key={r.id}>
                          <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                            {formatDate(r.created_at)}
                          </TableCell>
                          <TableCell className="font-mono text-xs font-semibold whitespace-nowrap">
                            {r.request_number ?? "—"}
                          </TableCell>
                          <TableCell className="text-sm whitespace-nowrap">
                            {CATEGORY_LABELS[r.category]}
                          </TableCell>
                          <TableCell><RemarkFileNumbers r={r} /></TableCell>
                          <TableCell className="text-sm max-w-64">
                            {r.remark}
                            <span className="text-xs text-muted-foreground"> — {r.created_by_name ?? "?"}</span>
                          </TableCell>
                          {isDecider && (
                            <TableCell>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setResolveTarget(r)}
                                disabled={resolveRemark.isPending}
                              >
                                Resolve
                              </Button>
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
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
                description="Raised remarks and their resolutions will appear here."
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Raised</TableHead>
                      <TableHead>Request #</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>File numbers</TableHead>
                      <TableHead>Remark</TableHead>
                      <TableHead>Status / Response</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {remarks.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(r.created_at)}
                        </TableCell>
                        <TableCell className="font-mono text-xs font-semibold whitespace-nowrap">
                          {r.request_number ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm whitespace-nowrap">
                          {CATEGORY_LABELS[r.category]}
                        </TableCell>
                        <TableCell><RemarkFileNumbers r={r} /></TableCell>
                        <TableCell className="text-sm max-w-64">{r.remark}</TableCell>
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
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      <ResolveDialog
        remark={resolveTarget}
        onClose={() => setResolveTarget(null)}
        onConfirm={doResolve}
        busy={resolveRemark.isPending}
      />
    </RoleGuard>
  );
}

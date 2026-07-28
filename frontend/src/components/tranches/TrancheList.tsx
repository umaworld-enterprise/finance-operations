"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ExternalLink, Lock, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { usePayTranche, useUpdateTranche, useUploadTrancheTtCopy } from "@/hooks/useRequests";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { PaymentTranche } from "@/types";

interface Props {
  requestId: string;
  tranches: PaymentTranche[];
  currency: string | null;
  /**
   * merchandiser — owner may edit amount / tentative date of UNPAID tranches;
   * accounts — may mark an unpaid tranche paid and upload its TT copy;
   * readonly — display only.
   */
  mode: "merchandiser" | "accounts" | "readonly";
}

function TrancheStatusPill({ status }: { status: PaymentTranche["status"] }) {
  return status === "paid" ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
      <CheckCircle2 className="h-3 w-3" /> Paid
    </span>
  ) : (
    <span className="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
      Unpaid
    </span>
  );
}

export function TrancheList({ requestId, tranches, currency, mode }: Props) {
  const updateTranche = useUpdateTranche(requestId);
  const payTranche = usePayTranche(requestId);
  const uploadTt = useUploadTrancheTtCopy(requestId);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editAmount, setEditAmount] = useState("");
  const [editDate, setEditDate] = useState("");
  const [payConfirmId, setPayConfirmId] = useState<string | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});
  const [selectedFiles, setSelectedFiles] = useState<Record<string, File | null>>({});

  const startEdit = (t: PaymentTranche) => {
    setEditingId(t.id);
    setEditAmount(String(t.amount));
    setEditDate(t.tentative_payment_date ?? "");
  };

  const saveEdit = async (t: PaymentTranche) => {
    const amount = Number(editAmount);
    if (!amount || amount <= 0) {
      toast.error("Tranche amount must be a positive number.");
      return;
    }
    if (!editDate) {
      toast.error("A tentative payment date is required.");
      return;
    }
    try {
      await updateTranche.mutateAsync({
        trancheId: t.id,
        data: { amount, tentative_payment_date: editDate },
      });
      toast.success(`${t.label} updated — the Accounts team has been notified.`);
      setEditingId(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update tranche.");
    }
  };

  const doPay = async (trancheId: string) => {
    const t = tranches.find((x) => x.id === trancheId);
    try {
      await payTranche.mutateAsync(trancheId);
      toast.success(`${t?.label ?? "Tranche"} marked as paid — the merchandiser has been notified.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to process tranche payment.");
    } finally {
      setPayConfirmId(null);
    }
  };

  const doUpload = async (t: PaymentTranche) => {
    const file = selectedFiles[t.id];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      toast.error("TT copy file must be 10 MB or smaller.");
      return;
    }
    setUploadingId(t.id);
    try {
      await uploadTt.mutateAsync({ trancheId: t.id, file });
      setSelectedFiles((prev) => ({ ...prev, [t.id]: null }));
      const input = fileInputs.current[t.id];
      if (input) input.value = "";
      toast.success(
        t.status === "unpaid"
          ? `TT copy uploaded — ${t.label} is now marked paid and the merchandiser has been notified.`
          : `TT copy uploaded for ${t.label} — the merchandiser has been notified.`,
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "TT copy upload failed.");
    } finally {
      setUploadingId(null);
    }
  };

  if (tranches.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No tranches recorded for this request.
      </p>
    );
  }

  const paidCount = tranches.filter((t) => t.status === "paid").length;

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {paidCount} of {tranches.length} tranche{tranches.length === 1 ? "" : "s"} paid.
      </p>
      <ul className="space-y-3">
        {tranches.map((t) => {
          const isEditing = editingId === t.id;
          return (
            <li key={t.id} className="rounded-lg border border-border p-3 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">{t.label}</span>
                <TrancheStatusPill status={t.status} />
                {t.status === "paid" && (
                  <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Lock className="h-3 w-3" /> Locked against edits
                  </span>
                )}
                {t.is_legacy && (
                  <span className="text-[10px] text-muted-foreground border border-border rounded-full px-2 py-0.5">
                    Migrated record
                  </span>
                )}
              </div>

              {isEditing ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Amount</p>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={editAmount}
                      onChange={(e) => setEditAmount(e.target.value)}
                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Tentative payment date</p>
                    <input
                      type="date"
                      value={editDate}
                      onChange={(e) => setEditDate(e.target.value)}
                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <div className="flex items-end gap-2">
                    <Button size="sm" onClick={() => saveEdit(t)} disabled={updateTranche.isPending}>
                      {updateTranche.isPending ? "Saving…" : "Save"}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Amount</dt>
                    <dd className="font-medium text-foreground">
                      {formatCurrency(t.amount, currency ?? undefined)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">% of invoice</dt>
                    <dd className="font-medium text-foreground">
                      {t.percentage_of_invoice != null ? `${t.percentage_of_invoice}%` : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Tentative date</dt>
                    <dd className="font-medium text-foreground">
                      {t.tentative_payment_date ? formatDate(t.tentative_payment_date) : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">
                      {t.status === "paid" ? "Paid on" : "TT copy"}
                    </dt>
                    <dd className="font-medium text-foreground">
                      {t.status === "paid" ? (
                        t.paid_at ? formatDate(t.paid_at) : "—"
                      ) : (
                        "—"
                      )}
                    </dd>
                  </div>
                </dl>
              )}

              {t.tt_copy_url && !isEditing && (
                <a
                  href={t.tt_copy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-secondary text-secondary-foreground text-xs font-medium hover:bg-muted transition-colors"
                >
                  View TT copy{t.tt_copy_filename ? ` — ${t.tt_copy_filename}` : ""}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}

              {/* Merchandiser: edit unpaid tranches on own request */}
              {mode === "merchandiser" && t.status === "unpaid" && !isEditing && (
                <Button size="sm" variant="outline" onClick={() => startEdit(t)}>
                  <Pencil className="h-3.5 w-3.5 mr-1.5" /> Edit amount / date
                </Button>
              )}

              {/* Accounts: pay + upload TT copy against this tranche */}
              {mode === "accounts" && t.status === "unpaid" && (
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
                  <Button
                    size="sm"
                    onClick={() => setPayConfirmId(t.id)}
                    disabled={payTranche.isPending}
                  >
                    Mark {t.label} Paid
                  </Button>
                  <input
                    ref={(el) => { fileInputs.current[t.id] = el; }}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                    onChange={(e) =>
                      setSelectedFiles((prev) => ({ ...prev, [t.id]: e.target.files?.[0] ?? null }))
                    }
                    className="flex-1 text-sm text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-border file:bg-secondary file:text-secondary-foreground file:text-xs file:font-medium file:cursor-pointer hover:file:bg-muted"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => doUpload(t)}
                    disabled={!selectedFiles[t.id] || uploadingId === t.id}
                  >
                    {uploadingId === t.id ? "Uploading…" : "Upload TT & Mark Paid"}
                  </Button>
                </div>
              )}
              {mode === "accounts" && t.status === "paid" && !t.tt_copy_url && (
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
                  <input
                    ref={(el) => { fileInputs.current[t.id] = el; }}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                    onChange={(e) =>
                      setSelectedFiles((prev) => ({ ...prev, [t.id]: e.target.files?.[0] ?? null }))
                    }
                    className="flex-1 text-sm text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-border file:bg-secondary file:text-secondary-foreground file:text-xs file:font-medium file:cursor-pointer hover:file:bg-muted"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => doUpload(t)}
                    disabled={!selectedFiles[t.id] || uploadingId === t.id}
                  >
                    {uploadingId === t.id ? "Uploading…" : "Upload TT Copy"}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <ConfirmDialog
        open={payConfirmId !== null}
        onOpenChange={(open) => !open && setPayConfirmId(null)}
        title="Mark this tranche as paid?"
        description="The merchandiser will be notified and the tranche will be locked against edits. Paying the final unpaid tranche completes the request and locks the record."
        confirmLabel="Yes, mark paid"
        onConfirm={() => payConfirmId && doPay(payConfirmId)}
      />
    </div>
  );
}

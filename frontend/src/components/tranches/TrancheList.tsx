"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Circle, ExternalLink, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DecisionDialog } from "@/components/hom/DecisionDialog";
import {
  useAddTranche,
  useDeleteTranche,
  usePayTranche,
  useRejectTranche,
  useUpdateTranche,
  useUpdateTranchePaymentDetails,
  useUploadTrancheTtCopy,
} from "@/hooks/useRequests";
import { useBanks } from "@/hooks/useMasters";
import { currencyDisplayLabel, formatCurrency, formatDate, todayLocalISO } from "@/lib/utils";
import type { PaymentTranche } from "@/types";

interface Props {
  requestId: string;
  tranches: PaymentTranche[];
  currency: string | null;
  /**
   * merchandiser — owner may edit/add/delete UNPAID tranches while the
   *   request is pending and untouched by Accounts (canModify);
   * accounts — may mark an unpaid tranche paid and upload its TT copy;
   * readonly — display only.
   */
  mode: "merchandiser" | "accounts" | "readonly";
  /** merchandiser mode: whether tranche changes are still allowed. */
  canModify?: boolean;
  /** merchandiser mode: why changes are blocked (shown when canModify is false). */
  modifyBlockedReason?: string | null;
  /** merchandiser mode: adding replacement tranches stays allowed while a
   * rejected tranche exists, even when canModify is false (Aug 2026). */
  canAdd?: boolean;
  /** accounts mode: called after the FINAL unpaid tranche is marked paid —
   * the request just completed and locked (UAT Aug 2026, item 10: return
   * to the queue automatically). */
  onRequestCompleted?: () => void;
}

// Accounts: per-tranche payment details entry (payment date + bank required
// before Mark Paid; reference number optional). Own component so each tranche
// keeps its own draft state.
function TranchePaymentDetailsForm({
  requestId,
  tranche,
  currency,
}: {
  requestId: string;
  tranche: PaymentTranche;
  currency: string | null;
}) {
  const updateDetails = useUpdateTranchePaymentDetails(requestId);
  // Bank master (Aug 2026): the master stores names only — options are
  // composed with the REQUEST currency ("DBS (EUR)", sign shown in front).
  // Dropdown-only by client decision: no free-text fallback.
  const { data: banks = [] } = useBanks();
  const composeBank = (name: string) => (currency ? `${name} (${currency})` : name);
  const [paymentDate, setPaymentDate] = useState(tranche.payment_date ?? "");
  const [bank, setBank] = useState(tranche.bank ?? "");
  const [reference, setReference] = useState(tranche.payment_reference_number ?? "");
  const [remarks, setRemarks] = useState(tranche.accounts_remarks ?? "");

  const inputCls =
    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  const save = async () => {
    if (!paymentDate || !bank.trim()) {
      toast.error("Payment date and bank are required.");
      return;
    }
    try {
      await updateDetails.mutateAsync({
        trancheId: tranche.id,
        data: {
          payment_date: paymentDate,
          bank: bank.trim(),
          payment_reference_number: reference.trim() || undefined,
          accounts_remarks: remarks.trim() || undefined,
        },
      });
      toast.success(`Payment details saved for ${tranche.label}.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save payment details.");
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <p className="text-xs text-muted-foreground mb-1">
            Payment date<span className="text-foreground ml-0.5" aria-hidden="true">*</span>
          </p>
          <input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} className={inputCls} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1">
            Bank<span className="text-foreground ml-0.5" aria-hidden="true">*</span>
          </p>
          <select
            value={bank}
            onChange={(e) => setBank(e.target.value)}
            disabled={banks.length === 0}
            className={inputCls}
          >
            <option value="" disabled>
              {banks.length === 0 ? "No banks configured" : "Select bank"}
            </option>
            {/* Legacy free-text value from before the master — keep visible */}
            {bank && !banks.some((b) => composeBank(b.name) === bank) && (
              <option value={bank} disabled>{bank} (legacy)</option>
            )}
            {banks.map((b) => (
              <option key={b.id} value={composeBank(b.name)}>
                {composeBank(b.name)}
              </option>
            ))}
          </select>
          {banks.length === 0 && (
            <p className="text-xs text-destructive mt-1">
              No banks configured — ask an administrator to add banks before
              recording payment details.
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1">Payment ref. # (optional)</p>
          <input type="text" value={reference} onChange={(e) => setReference(e.target.value)} className={inputCls} />
        </div>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <p className="text-xs text-muted-foreground mb-1">Accounts remarks (optional)</p>
          <input
            type="text"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="Internal note for this tranche payment"
            className={inputCls}
          />
        </div>
        <div className="flex items-end">
          <Button size="sm" variant="secondary" onClick={save} disabled={updateDetails.isPending}>
            {updateDetails.isPending ? "Saving…" : "Save Details"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ReadinessItem({ done, label }: { done: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${done ? "text-emerald-700" : "text-muted-foreground"}`}>
      {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}
      {label}
    </span>
  );
}

function TrancheStatusPill({ status }: { status: PaymentTranche["status"] }) {
  if (status === "paid") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
        <CheckCircle2 className="h-3 w-3" /> Paid
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="inline-flex items-center text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
        Rejected
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
      Unpaid
    </span>
  );
}

export function TrancheList({
  requestId,
  tranches,
  currency,
  mode,
  canModify = true,
  modifyBlockedReason = null,
  canAdd,
  onRequestCompleted,
}: Props) {
  const updateTranche = useUpdateTranche(requestId);
  const uploadTt = useUploadTrancheTtCopy(requestId);
  const addTranche = useAddTranche(requestId);
  const deleteTranche = useDeleteTranche(requestId);
  const payTranche = usePayTranche(requestId);
  const rejectTranche = useRejectTranche(requestId);
  const [payConfirmId, setPayConfirmId] = useState<string | null>(null);
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editAmount, setEditAmount] = useState("");
  const [editDate, setEditDate] = useState("");
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addAmount, setAddAmount] = useState("");
  const [addDate, setAddDate] = useState(todayLocalISO());

  const merchandiserCanModify = mode === "merchandiser" && canModify;
  // Adding replacement tranches stays possible after a rejection even when
  // other changes are frozen (Aug 2026 rejection workflow).
  const merchandiserCanAdd = mode === "merchandiser" && (canAdd ?? canModify);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

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

  const doAdd = async () => {
    const amount = Number(addAmount);
    if (!amount || amount <= 0) {
      toast.error("Tranche amount must be a positive number.");
      return;
    }
    if (!addDate) {
      toast.error("A tentative payment date is required.");
      return;
    }
    try {
      await addTranche.mutateAsync({ amount, tentative_payment_date: addDate });
      toast.success("Tranche added — the Accounts team has been notified.");
      setAddOpen(false);
      setAddAmount("");
      setAddDate(todayLocalISO());
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to add tranche.");
    }
  };

  const doDelete = async (t: PaymentTranche) => {
    try {
      await deleteTranche.mutateAsync(t.id);
      toast.success(`${t.label} deleted — the Accounts team has been notified.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to delete tranche.");
    }
  };

  const doReject = async (reason: string) => {
    if (!rejectTargetId) return;
    const t = tranches.find((x) => x.id === rejectTargetId);
    try {
      await rejectTranche.mutateAsync({ trancheId: rejectTargetId, reason });
      toast.success(
        `${t?.label ?? "Tranche"} rejected — the merchandiser has been notified and can add replacement tranches.`,
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to reject the tranche.");
    }
  };

  const doPay = async (trancheId: string) => {
    const t = tranches.find((x) => x.id === trancheId);
    // Is this the last unpaid live tranche? Paying it completes the request.
    const wasFinal = tranches.filter((x) => x.status === "unpaid").length === 1;
    try {
      await payTranche.mutateAsync(trancheId);
      if (wasFinal) {
        toast.success("Final tranche paid — payment completed and the request is locked.");
        onRequestCompleted?.();
      } else {
        toast.success(`${t?.label ?? "Tranche"} marked as paid — the merchandiser has been notified.`);
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to mark the tranche paid.");
    } finally {
      setPayConfirmId(null);
    }
  };

  // One-click flow (10 Aug follow-up): the Upload TT Copy button opens the
  // file picker directly and the upload starts the moment a file is chosen —
  // no separate Choose File step, no "No file selected" state.
  const doUpload = async (t: PaymentTranche, file: File) => {
    if (file.size > 10 * 1024 * 1024) {
      toast.error("TT copy file must be 10 MB or smaller.");
      return;
    }
    setUploadingId(t.id);
    try {
      await uploadTt.mutateAsync({ trancheId: t.id, file });
      // No notification fires on upload (4 Aug fix) — the merchandiser is
      // notified once, when the tranche is explicitly marked paid.
      toast.success(
        `TT copy uploaded for ${t.label}.` +
          (t.status === "unpaid" ? " Click Mark Paid once payment details are also recorded." : ""),
      );
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "TT copy upload failed.");
    } finally {
      setUploadingId(null);
      const input = fileInputs.current[t.id];
      if (input) input.value = "";
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
  const rejectedCount = tranches.filter((t) => t.status === "rejected").length;
  const liveCount = tranches.length - rejectedCount;

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {paidCount} of {liveCount} tranche{liveCount === 1 ? "" : "s"} paid
        {rejectedCount > 0 ? ` · ${rejectedCount} rejected` : ""}.
      </p>
      <ul className="space-y-3">
        {tranches.map((t) => {
          const isEditing = editingId === t.id;
          const isRejected = t.status === "rejected";
          return (
            <li
              key={t.id}
              className={
                isRejected
                  ? "rounded-lg border border-red-200 bg-red-50/40 p-3 space-y-2 opacity-90"
                  : "rounded-lg border border-border p-3 space-y-2"
              }
            >
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

              {/* Rejected tranches stay visible for record-keeping, reason
                  prominent, all actions disabled (Aug 2026). */}
              {isRejected && (
                <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-800">
                  <span className="font-semibold">Rejected by Accounts</span>
                  {t.rejected_at ? ` on ${formatDate(t.rejected_at)}` : ""} —{" "}
                  {t.rejection_reason || "no reason recorded"}. This tranche no longer
                  counts toward the request total.
                </div>
              )}

              {isEditing ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">
                      {currency ? `Amount (${currencyDisplayLabel(currency)})` : "Amount"}
                    </p>
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

              {/* Merchandiser: edit/delete unpaid tranches while the request
                  is pending and untouched by Accounts */}
              {merchandiserCanModify && t.status === "unpaid" && !isEditing && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => startEdit(t)}>
                    <Pencil className="h-3.5 w-3.5 mr-1.5" /> Edit amount / date
                  </Button>
                  {tranches.length > 1 && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => doDelete(t)}
                      disabled={deleteTranche.isPending}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
                    </Button>
                  )}
                </div>
              )}

              {/* Accounts: TT copy + payment details are both mandatory, then
                  an EXPLICIT Mark Paid click changes the status (Aug 2026,
                  item 3.1 — uploads never auto-pay). */}
              {mode === "accounts" && t.status === "unpaid" && (
                <div className="space-y-3 pt-2 mt-1 border-t border-border">
                  <TranchePaymentDetailsForm requestId={requestId} tranche={t} currency={currency} />

                  {!t.tt_copy_url && (
                    <div className="flex">
                      {/* Hidden native input — the single Upload button opens
                          the picker and the chosen file uploads immediately. */}
                      <input
                        ref={(el) => { fileInputs.current[t.id] = el; }}
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void doUpload(t, file);
                        }}
                        className="hidden"
                      />
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => fileInputs.current[t.id]?.click()}
                        disabled={uploadingId === t.id}
                      >
                        {uploadingId === t.id ? "Uploading…" : "Upload TT Copy"}
                      </Button>
                    </div>
                  )}

                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-3 flex-wrap">
                      <ReadinessItem done={!!t.tt_copy_url} label="TT copy uploaded" />
                      <ReadinessItem
                        done={!!t.payment_date && !!t.bank}
                        label="Payment details recorded"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setRejectTargetId(t.id)}
                        disabled={rejectTranche.isPending || payTranche.isPending}
                      >
                        Reject {t.label}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => setPayConfirmId(t.id)}
                        disabled={
                          !t.tt_copy_url || !t.payment_date || !t.bank || payTranche.isPending
                        }
                      >
                        Mark {t.label} Paid
                      </Button>
                    </div>
                  </div>
                </div>
              )}
              {mode === "accounts" && t.status === "paid" && !t.tt_copy_url && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-amber-700">
                    Legacy record — this tranche was marked paid before TT copies became
                    mandatory. Upload its TT copy to complete the record.
                  </p>
                  <div className="flex">
                    <input
                      ref={(el) => { fileInputs.current[t.id] = el; }}
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void doUpload(t, file);
                      }}
                      className="hidden"
                    />
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => fileInputs.current[t.id]?.click()}
                      disabled={uploadingId === t.id}
                    >
                      {uploadingId === t.id ? "Uploading…" : "Upload TT Copy"}
                    </Button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* Merchandiser: changes frozen once Accounts act on the request */}
      {mode === "merchandiser" && !canModify && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
          {merchandiserCanAdd
            ? "A tranche was rejected — add replacement tranches below until the total matches the required amount again. Existing tranches stay locked."
            : `Tranches can no longer be changed${modifyBlockedReason ? ` — ${modifyBlockedReason}.` : "."} Contact the Accounts team if an amount or date is wrong.`}
        </p>
      )}

      {/* Merchandiser: add a tranche while allowed — including replacement
          tranches after a rejection (Aug 2026). */}
      {merchandiserCanAdd && (
        addOpen ? (
          <div className="rounded-lg border border-dashed border-border p-3 space-y-2">
            <p className="text-sm font-semibold text-foreground">New Deposit Tranche</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <p className="text-xs text-muted-foreground mb-1">
                  {currency ? `Amount (${currencyDisplayLabel(currency)})` : "Amount"}
                </p>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  value={addAmount}
                  onChange={(e) => setAddAmount(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-1">Tentative payment date</p>
                <input
                  type="date"
                  value={addDate}
                  onChange={(e) => setAddDate(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="flex items-end gap-2">
                <Button size="sm" onClick={doAdd} disabled={addTranche.isPending}>
                  {addTranche.isPending ? "Adding…" : "Add"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAddOpen(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Tranche
          </Button>
        )
      )}

      <ConfirmDialog
        open={payConfirmId !== null}
        onOpenChange={(open) => !open && setPayConfirmId(null)}
        title="Mark this tranche as paid?"
        description="Its TT copy and payment details are recorded. The merchandiser will be notified and the tranche will be locked against edits. Paying the final unpaid tranche completes the request and locks the record."
        confirmLabel="Yes, mark paid"
        onConfirm={() => payConfirmId && doPay(payConfirmId)}
      />

      <DecisionDialog
        open={rejectTargetId !== null}
        title="Reject Tranche"
        description="The tranche stays visible as a rejected record and its amount stops counting toward the request total. The merchandiser will be notified with your reason and can add replacement tranches."
        placeholder="Reason for rejection (e.g. wrong amount entered)"
        confirmLabel="Confirm Reject"
        destructive
        busy={rejectTranche.isPending}
        onClose={() => setRejectTargetId(null)}
        onConfirm={doReject}
      />
    </div>
  );
}

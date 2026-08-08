"use client";

import { useParams } from "next/navigation";
import { toast } from "sonner";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { TrancheList } from "@/components/tranches/TrancheList";
import { SupplierDefaultHistory } from "@/components/forms/SupplierDefaultHistory";
import { RequestAuditTrail } from "@/components/tranches/RequestAuditTrail";
import { RequestAdjustments } from "@/components/tranches/RequestAdjustments";
import { useRequest, useRequestAction, useFieldVisibility, useUpdateRemarks, usePayment, useTranchesModifiable, useUpdateRequest } from "@/hooks/useRequests";
import { formatCurrency, formatDate } from "@/lib/utils";
import { useState, useEffect } from "react";
import { ArrowLeft, Lock, FileQuestion, ExternalLink } from "lucide-react";
import Link from "next/link";

export default function MerchandiserRequestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: req, isLoading } = useRequest(id);
  const { data: payment } = usePayment(id);
  const { data: modifiable } = useTranchesModifiable(id);
  const { data: fv = {} } = useFieldVisibility();
  const { mutateAsync: performAction, isPending } = useRequestAction();
  const { mutateAsync: saveRemarks, isPending: savingRemarks } = useUpdateRemarks(id);
  const [remarks, setRemarks] = useState("");
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [merchandiserNote, setMerchandiserNote] = useState("");

  // Editable invoice numbers (Aug 2026 follow-up, item 4) — while the request
  // is still pending and untouched by Accounts. Duplicates rejected server-side.
  const { mutateAsync: updateRequest, isPending: savingInvoices } = useUpdateRequest(id);
  const [sunshineDraft, setSunshineDraft] = useState("");
  const [supplierInvDraft, setSupplierInvDraft] = useState("");
  useEffect(() => {
    setSunshineDraft(req?.sunshine_invoice_number ?? "");
    setSupplierInvDraft(req?.supplier_invoice_number ?? "");
  }, [req?.sunshine_invoice_number, req?.supplier_invoice_number]);

  const invoiceChanges: { sunshine_invoice_number?: string; supplier_invoice_number?: string } = {};
  if (sunshineDraft.trim() && sunshineDraft.trim() !== (req?.sunshine_invoice_number ?? "")) {
    invoiceChanges.sunshine_invoice_number = sunshineDraft.trim();
  }
  if (supplierInvDraft.trim() && supplierInvDraft.trim() !== (req?.supplier_invoice_number ?? "")) {
    invoiceChanges.supplier_invoice_number = supplierInvDraft.trim();
  }

  const doSaveInvoiceNumbers = async () => {
    if (Object.keys(invoiceChanges).length === 0) return;
    try {
      await updateRequest(invoiceChanges);
      toast.success("Invoice numbers updated — the change is recorded in the audit log.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update invoice numbers.");
    }
  };

  const snap = req?.analytics_snapshot;

  // Sync textarea with loaded remarks — also re-sync when the content changes
  // so the textarea refreshes if an admin updates the same request in another tab.
  useEffect(() => {
    if (req?.remarks !== undefined) setMerchandiserNote(req.remarks ?? "");
  }, [req?.id, req?.remarks]); // eslint-disable-line react-hooks/exhaustive-deps

  // Terminal statuses: the request is closed to the merchandiser entirely
  // (UAT Aug 2026, item 18) — no edits, not even remarks.
  const requestClosed =
    req?.current_status === "rejected_by_accounts" ||
    req?.current_status === "rejected_by_hom" ||
    req?.current_status === "cancelled_by_merchandiser" ||
    req?.current_status === "cancelled_by_accounts";

  const canHold =
    req?.current_status === "pending_payment" && !req.is_locked;
  const canResume =
    req?.current_status === "hold_by_merchandiser" && !req.is_locked;
  // pending_hom_approval: merchandiser may withdraw the request while it
  // awaits Head of Merchandiser review (backend allows this transition).
  const canCancel =
    (req?.current_status === "pending_payment" ||
      req?.current_status === "hold_by_merchandiser" ||
      req?.current_status === "pending_hom_approval") &&
    !req.is_locked;

  const doSaveRemarks = async () => {
    try {
      await saveRemarks(merchandiserNote);
      toast.success("Remark saved.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save remark.");
    }
  };

  const doAction = async (action: "hold" | "resume" | "cancel") => {
    // Optimistic status: the UI flips immediately; the server reconciles.
    const optimistic = {
      hold: "hold_by_merchandiser",
      resume: "pending_payment",
      cancel: "cancelled_by_merchandiser",
    } as const;
    try {
      await performAction({ id, action, remarks, optimisticStatus: optimistic[action] });
      toast.success("Action completed.");
      setRemarks("");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed.");
    }
  };

  if (isLoading) {
    return (
      <>
        <TopNav title="Request" />
        <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-7 w-48" />
          <Card>
            <CardContent className="p-6 space-y-4">
              <Skeleton className="h-4 w-32" />
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-5">
                {Array.from({ length: 9 }).map((_, i) => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-4 w-28" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </main>
      </>
    );
  }

  if (!req) {
    return (
      <>
        <TopNav title="Request" />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <EmptyState
            icon={FileQuestion}
            title="Request not found"
            description="This request may have been deleted or you don't have access to it."
            action={
              <Button asChild variant="outline">
                <Link href="/merchandiser">Back to my requests</Link>
              </Button>
            }
          />
        </main>
      </>
    );
  }

  const field = (label: string, value: React.ReactNode) => (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-foreground">{value ?? "—"}</dd>
    </div>
  );

  return (
    <RoleGuard allowedRoles={["merchandiser", "super_admin"]}>
      <TopNav title={`Request ${req.request_number}`} />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
        <Link
          href="/merchandiser"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to my requests
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-foreground">{req.request_number}</h1>
          <StatusBadge status={req.current_status} showFull />
          {req.is_locked && (
            <span className="inline-flex items-center gap-1 text-xs text-foreground bg-muted border border-border px-2 py-0.5 rounded-full">
              <Lock className="h-3 w-3" /> Locked
            </span>
          )}
        </div>

        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="text-sm font-semibold text-foreground mb-4">Request Details</h2>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-5">
              {field("Supplier", req.supplier.name)}
              {field("Customer", req.customer.name)}
              {field("Vertical", req.vertical?.name)}
              {field("Currency", req.currency)}
              {fv.deposit_amount !== false && field("Deposit Amount", formatCurrency(req.deposit_amount, req.currency))}
              {fv.deposit_percentage !== false && field("Deposit %", `${req.deposit_percentage}%`)}
              {fv.total_supplier_invoice_amount !== false && field("Total Invoice Amount", formatCurrency(req.total_supplier_invoice_amount, req.currency))}
              {fv.exchange_rate !== false && req.exchange_rate != null && field("Exchange Rate", req.exchange_rate)}
              {field("Sunshine Invoice #", req.sunshine_invoice_number)}
              {field("Supplier Proforma Invoice #", req.supplier_invoice_number)}
              {field("Estimated ETD", req.estimated_etd ? formatDate(req.estimated_etd) : null)}
              {req.payment_terms && field("Payment Terms", req.payment_terms)}
              {field("Submission Source", req.submission_source)}
              {field("Created", formatDate(req.created_at))}
              {field("Last Updated", formatDate(req.updated_at))}
              {fv.creator_info !== false && field("Submitted By", req.creator ? `${req.creator.full_name} (${req.creator.email})` : req.submitter_email ?? null)}
              {payment?.tt_copy_url && field(
                "TT Copy",
                <a
                  href={payment.tt_copy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline underline-offset-2 hover:opacity-80"
                >
                  View TT copy
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </dl>
          </CardContent>
        </Card>

        {/* Invoice numbers — editable while pending and untouched by Accounts
            (Aug 2026 follow-up, item 4). */}
        {modifiable?.modifiable && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-3">
              <div>
                <h2 className="font-semibold text-foreground text-sm">Invoice Numbers</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Editable while the request is pending and the Accounts team has not
                  started processing. A number already used by another live request
                  is rejected.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="edit-sunshine-invoice">Sunshine Invoice #</Label>
                  <input
                    id="edit-sunshine-invoice"
                    type="text"
                    value={sunshineDraft}
                    onChange={(e) => setSunshineDraft(e.target.value)}
                    className="mt-1 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div>
                  <Label htmlFor="edit-supplier-invoice">Supplier Proforma Invoice #</Label>
                  <input
                    id="edit-supplier-invoice"
                    type="text"
                    value={supplierInvDraft}
                    onChange={(e) => setSupplierInvDraft(e.target.value)}
                    className="mt-1 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
              </div>
              <Button
                size="sm"
                onClick={doSaveInvoiceNumbers}
                disabled={savingInvoices || Object.keys(invoiceChanges).length === 0}
              >
                {savingInvoices ? "Saving…" : "Save Invoice Numbers"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Advance Payment Tranches — unpaid tranches stay editable by the
            request owner; paid tranches are locked. */}
        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="text-sm font-semibold text-foreground mb-1">Advance Payment Tranches</h2>
            <p className="text-xs text-muted-foreground mb-4">
              You can edit, add or delete tranches while the request is pending and
              the Accounts team has not started processing it. The Accounts team is
              notified of every change.
            </p>
            <TrancheList
              requestId={id}
              tranches={req.tranches ?? []}
              currency={req.currency}
              mode={
                req.is_locked ||
                ["cancelled_by_merchandiser", "cancelled_by_accounts", "rejected_by_hom"].includes(
                  req.current_status,
                )
                  ? "readonly"
                  : "merchandiser"
              }
              canModify={modifiable?.modifiable ?? false}
              modifyBlockedReason={modifiable?.reason ?? null}
              canAdd={modifiable?.can_add ?? false}
            />
          </CardContent>
        </Card>

        <RequestAdjustments requestId={id} currency={req.currency} linkBase="/merchandiser" />

        {snap && (fv.grace_etd !== false || fv.etd_grace_overdue_days !== false || fv.actual_etd_overdue_days !== false || fv.default_status !== false) && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="text-sm font-semibold text-foreground mb-4">Analytics</h2>
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-5">
                {fv.grace_etd !== false && field("Grace ETD", formatDate(snap.grace_etd))}
                {fv.etd_grace_overdue_days !== false && field("ETD Grace Overdue Days", snap.etd_grace_overdue_days != null ? `${snap.etd_grace_overdue_days}d` : null)}
                {fv.actual_etd_overdue_days !== false && field("Actual ETD Overdue Days", snap.actual_etd_overdue_days != null ? `${snap.actual_etd_overdue_days}d` : null)}
                {fv.default_status !== false && field("Risk Status", snap.default_status)}
              </dl>
            </CardContent>
          </Card>
        )}

        {/* Supplier default track record */}
        <SupplierDefaultHistory supplierId={req.supplier.id} supplierName={req.supplier.name} />

        {fv.status_history !== false && req.status_history && req.status_history.length > 0 && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="text-sm font-semibold text-foreground mb-4">Status History</h2>
              <ol className="space-y-3">
                {req.status_history.map((h) => (
                  <li key={h.id} className="flex flex-col sm:flex-row gap-1 sm:gap-3 text-sm">
                    <span className="text-muted-foreground shrink-0 sm:w-32 text-xs pt-0.5">
                      {formatDate(h.changed_at)}
                    </span>
                    <span className="flex-1">
                      {h.old_status ? (
                        <>
                          <StatusBadge status={h.old_status} />
                          <span className="mx-1.5 text-muted-foreground">→</span>
                        </>
                      ) : null}
                      <StatusBadge status={h.new_status} showFull />
                      {h.remarks && (
                        <p className="text-xs text-muted-foreground mt-0.5">{h.remarks}</p>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        )}

        {/* Merchandiser remarks — editable until the request is rejected or
            cancelled (terminal statuses close the request entirely,
            UAT Aug 2026 item 18). */}
        <Card>
          <CardContent className="p-5 md:p-6 space-y-3">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Remarks</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {requestClosed
                  ? "This request is closed — remarks can no longer be changed."
                  : "Leave a note for the accounts team — visible to all roles. You cannot edit the form fields once submitted."}
              </p>
            </div>
            <Textarea
              value={merchandiserNote}
              onChange={(e) => setMerchandiserNote(e.target.value)}
              rows={3}
              placeholder="e.g. Please update the deposit % to 30 — confirmed with supplier."
              disabled={requestClosed}
            />
            {!requestClosed && (
              <Button
                size="sm"
                onClick={doSaveRemarks}
                disabled={savingRemarks}
                className="w-full sm:w-auto"
              >
                {savingRemarks ? "Saving…" : "Save Remark"}
              </Button>
            )}
          </CardContent>
        </Card>

        <RequestAuditTrail requestId={id} />

        {(canHold || canResume || canCancel) && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-4">
              <h2 className="text-sm font-semibold text-foreground">Actions</h2>
              <div>
                <Label htmlFor="action-remarks">Remarks (optional)</Label>
                <Textarea
                  id="action-remarks"
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  rows={2}
                />
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                {canHold && (
                  <Button variant="warning" onClick={() => doAction("hold")} disabled={isPending} className="w-full sm:w-auto">
                    Place on Hold
                  </Button>
                )}
                {canResume && (
                  <Button variant="secondary" onClick={() => doAction("resume")} disabled={isPending} className="w-full sm:w-auto">
                    Resume
                  </Button>
                )}
                {canCancel && (
                  <Button variant="destructive" onClick={() => setCancelConfirm(true)} disabled={isPending} className="w-full sm:w-auto">
                    Cancel Request
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </main>

      <ConfirmDialog
        open={cancelConfirm}
        onOpenChange={setCancelConfirm}
        title="Cancel this request?"
        description="This will cancel your Supplier Advance Payment Request. The Accounts team will be notified. This action may not be reversible."
        confirmLabel="Yes, cancel request"
        destructive
        onConfirm={() => doAction("cancel")}
      />
    </RoleGuard>
  );
}

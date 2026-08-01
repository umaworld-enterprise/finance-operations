"use client";

import { useParams } from "next/navigation";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PaymentForm } from "@/components/forms/PaymentForm";
import { TrancheList } from "@/components/tranches/TrancheList";
import { RequestAuditTrail } from "@/components/tranches/RequestAuditTrail";
import { RequestAdjustments } from "@/components/tranches/RequestAdjustments";
import { useRequest, usePayment, useRequestAction, useFieldVisibility, useUpdateRequest } from "@/hooks/useRequests";
import { useAuth } from "@/hooks/useAuth";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ArrowLeft, Lock, FileQuestion } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import { toast } from "sonner";

export default function AccountsPaymentPage() {
  const { id } = useParams<{ id: string }>();
  const { data: req, isLoading } = useRequest(id);
  const { data: payment } = usePayment(id);
  const { data: fv = {} } = useFieldVisibility();
  const { mutateAsync: performAction, isPending } = useRequestAction();
  const [holdRemarks, setHoldRemarks] = useState("");
  const { user } = useAuth();
  // Finance Admin may only record the ship date — everything else read-only.
  const isFinance = user?.role === "finance_admin";
  // Client rule (2026-07-11): invoice numbers can be UPDATED only by a Super
  // Admin; every change lands in the audit log with its old and new value.
  const isSuper = user?.role === "super_admin";

  const { mutateAsync: updateInvoiceNumbers, isPending: savingInvoices } = useUpdateRequest(id);
  const [sunshineInvoice, setSunshineInvoice] = useState("");
  const [supplierInvoice, setSupplierInvoice] = useState("");
  useEffect(() => {
    setSunshineInvoice(req?.sunshine_invoice_number ?? "");
    setSupplierInvoice(req?.supplier_invoice_number ?? "");
  }, [req?.sunshine_invoice_number, req?.supplier_invoice_number]);

  const invoiceChanges: { sunshine_invoice_number?: string; supplier_invoice_number?: string } = {};
  if (sunshineInvoice.trim() && sunshineInvoice.trim() !== (req?.sunshine_invoice_number ?? "")) {
    invoiceChanges.sunshine_invoice_number = sunshineInvoice.trim();
  }
  if (supplierInvoice.trim() && supplierInvoice.trim() !== (req?.supplier_invoice_number ?? "")) {
    invoiceChanges.supplier_invoice_number = supplierInvoice.trim();
  }

  const doSaveInvoiceNumbers = async () => {
    if (Object.keys(invoiceChanges).length === 0) return;
    try {
      await updateInvoiceNumbers(invoiceChanges);
      toast.success("Invoice number updated — the change is recorded in the audit log.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update invoice numbers.");
    }
  };

  const snap = req?.analytics_snapshot;

  // HoM decision (Aug 2026, item 3.5): the approval/rejection remark renders
  // like the merchandiser remarks do. A request that never went through HoM
  // has no pending_hom_approval transition, so this stays undefined.
  const homDecision = (req?.status_history ?? [])
    .filter((h) => h.old_status === "pending_hom_approval")
    .sort((a, b) => b.changed_at.localeCompare(a.changed_at))[0];

  const canHold   = req?.current_status === "pending_payment"      && !req.is_locked && !isFinance;
  // "reopened" must also offer Resume — otherwise a reopened request is
  // stranded with no path back to the payment queue.
  const canResume = (req?.current_status === "hold_by_accounts" || req?.current_status === "reopened") && !req.is_locked && !isFinance;
  const canCancel = req?.current_status === "hold_by_accounts"     && !req.is_locked && !isFinance;
  const canReopen = req?.current_status === "cancelled_by_accounts" && !req.is_locked && !isFinance;

  const doAction = async (action: "hold" | "resume" | "cancel" | "reopen") => {
    // Optimistic status: the UI flips immediately; the server reconciles.
    const optimistic = {
      hold: "hold_by_accounts",
      resume: "pending_payment",
      cancel: "cancelled_by_accounts",
      reopen: "reopened",
    } as const;
    try {
      await performAction({ id, action, remarks: holdRemarks, optimisticStatus: optimistic[action] });
      toast.success("Action completed.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed.");
    }
  };

  const field = (label: string, value: React.ReactNode) => (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground text-sm">{value ?? "—"}</dd>
    </div>
  );

  if (isLoading) {
    return (
      <>
        <TopNav title="Payment" />
        <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
          <Skeleton className="h-4 w-32" />
          <Card>
            <CardContent className="p-6 space-y-4">
              <Skeleton className="h-5 w-48" />
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-4 w-28" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <Skeleton className="h-40" />
            </CardContent>
          </Card>
        </main>
      </>
    );
  }

  if (!req) {
    return (
      <>
        <TopNav title="Payment" />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <EmptyState
            icon={FileQuestion}
            title="Request not found"
            description="This request may have been deleted or you don't have access to it."
            action={
              <Button asChild variant="outline">
                <Link href="/accounts">Back to queue</Link>
              </Button>
            }
          />
        </main>
      </>
    );
  }

  return (
    <RoleGuard allowedRoles={["accounts_team", "super_admin", "finance_admin"]}>
      <TopNav title={`Payment — ${req.request_number}`} />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
        <Link
          href="/accounts"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to queue
        </Link>

        <Card>
          <CardContent className="p-5 md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-semibold text-foreground">{req.request_number}</h2>
                <StatusBadge status={req.current_status} />
                {req.is_locked && (
                  <span className="inline-flex items-center gap-1 text-xs text-foreground bg-muted border border-border px-2 py-0.5 rounded-full">
                    <Lock className="h-3 w-3" /> Locked
                  </span>
                )}
              </div>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              {field("Supplier", req.supplier.name)}
              {field("Customer", req.customer.name)}
              {field("Vertical", req.vertical?.name)}
              {fv.deposit_amount !== false && field("Deposit Amount", formatCurrency(req.deposit_amount, req.currency ?? undefined))}
              {fv.deposit_percentage !== false && field("Deposit %", `${req.deposit_percentage}%`)}
              {fv.total_supplier_invoice_amount !== false && field("Total Invoice Amount", formatCurrency(req.total_supplier_invoice_amount, req.currency ?? undefined))}
              {fv.exchange_rate !== false && req.exchange_rate != null && field("Exchange Rate", req.exchange_rate)}
              {req.estimated_etd && field("Estimated ETD", formatDate(req.estimated_etd))}
              {field("Submitted", formatDate(req.created_at))}
              {req.payment_terms && field("Payment Terms", req.payment_terms)}
              {req.sunshine_invoice_number && field("Sunshine Invoice #", req.sunshine_invoice_number)}
              {req.supplier_invoice_number && field("Supplier Proforma Invoice #", req.supplier_invoice_number)}
              {fv.creator_info !== false && field("Submitted By", req.creator ? `${req.creator.full_name} (${req.creator.email})` : req.submitter_email ?? null)}
              {fv.accounts_timestamp !== false && payment && field("Payment Last Updated", formatDate(payment.updated_at))}
            </dl>
            {req.remarks && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs font-medium text-muted-foreground mb-1">Merchandiser Remarks</p>
                <p className="text-sm text-foreground bg-muted/50 rounded-lg px-3 py-2">{req.remarks}</p>
              </div>
            )}
            {homDecision && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Head of Merchandiser Decision —{" "}
                  {homDecision.new_status === "rejected_by_hom" ? "Rejected" : "Approved"}{" "}
                  ({formatDate(homDecision.changed_at)})
                </p>
                <p className="text-sm text-foreground bg-muted/50 rounded-lg px-3 py-2">
                  {homDecision.remarks || "No reason recorded."}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {isSuper && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-3">
              <div>
                <h2 className="font-semibold text-foreground text-sm">Invoice Numbers</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Only a Super Admin can update these. Every change is recorded in the
                  audit log with its old and new value.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="sunshine-invoice">Sunshine Invoice #</Label>
                  <input
                    id="sunshine-invoice"
                    type="text"
                    value={sunshineInvoice}
                    onChange={(e) => setSunshineInvoice(e.target.value)}
                    className="mt-1 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div>
                  <Label htmlFor="supplier-invoice">Supplier Proforma Invoice #</Label>
                  <input
                    id="supplier-invoice"
                    type="text"
                    value={supplierInvoice}
                    onChange={(e) => setSupplierInvoice(e.target.value)}
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

        {snap && (fv.grace_etd !== false || fv.etd_grace_overdue_days !== false || fv.actual_etd_overdue_days !== false || fv.payment_to_ship_days !== false || fv.payment_to_request_days !== false || fv.cost_of_fund !== false || fv.default_status !== false) && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="font-semibold text-foreground mb-4 text-sm">Analytics Snapshot</h2>
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                {fv.grace_etd !== false && field("Grace ETD", formatDate(snap.grace_etd))}
                {fv.etd_grace_overdue_days !== false && field("ETD Grace Overdue Days", snap.etd_grace_overdue_days != null ? `${snap.etd_grace_overdue_days}d` : null)}
                {fv.actual_etd_overdue_days !== false && field("Actual ETD Overdue Days", snap.actual_etd_overdue_days != null ? `${snap.actual_etd_overdue_days}d` : null)}
                {fv.payment_to_ship_days !== false && field("Payment → Ship Days", snap.payment_to_ship_days != null ? `${snap.payment_to_ship_days}d` : null)}
                {fv.payment_to_request_days !== false && field("Payment → Request Days", snap.payment_to_request_days != null ? `${snap.payment_to_request_days}d` : null)}
                {fv.cost_of_fund !== false && field("Cost of Fund", snap.cost_of_fund_amount != null ? formatCurrency(Number(snap.cost_of_fund_amount), req.currency ?? undefined) : null)}
                {fv.default_status !== false && field("Risk Status", snap.default_status)}
              </dl>
            </CardContent>
          </Card>
        )}

        {/* Advance Payment Tranches — Accounts pays tranche-by-tranche and
            uploads the TT copy against the specific tranche it paid. */}
        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="font-semibold text-foreground text-sm mb-1">Advance Payment Tranches</h2>
            <p className="text-xs text-muted-foreground mb-4">
              Select the unpaid tranche you processed and upload the bank&apos;s TT copy
              against it. The merchandiser is notified per tranche. Paying the final
              tranche completes and locks the request.
            </p>
            <TrancheList
              requestId={id}
              tranches={req.tranches ?? []}
              currency={req.currency}
              mode={
                isFinance ||
                ["cancelled_by_merchandiser", "cancelled_by_accounts", "rejected_by_hom"].includes(
                  req.current_status,
                )
                  ? "readonly"
                  : "accounts"
              }
            />
          </CardContent>
        </Card>

        <RequestAdjustments requestId={id} currency={req.currency} linkBase="/accounts" />

        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="font-semibold text-foreground mb-4">Payment Details</h2>
            {/* Cost of Fund surfaced at the point of processing (Aug 2026,
                item 3.4) — same fv gate as the Analytics Snapshot card. */}
            {fv.cost_of_fund !== false && snap && (
              <div className="mb-4 rounded-lg border border-border bg-muted/40 px-4 py-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
                <span className="text-sm">
                  <span className="text-muted-foreground">Cost of Fund:</span>{" "}
                  <span className="font-semibold text-foreground">
                    {snap.cost_of_fund_amount != null
                      ? formatCurrency(Number(snap.cost_of_fund_amount), req.currency ?? undefined)
                      : "—"}
                  </span>
                </span>
                {snap.grace_etd && (
                  <span className="text-xs text-muted-foreground">
                    Accrues past Grace ETD {formatDate(snap.grace_etd)}
                    {snap.etd_grace_overdue_days ? ` — ${snap.etd_grace_overdue_days}d overdue` : ""}
                  </span>
                )}
              </div>
            )}
            <PaymentForm requestId={id} isLocked={req.is_locked} existing={payment} readOnly={isFinance} trancheMode />
          </CardContent>
        </Card>

        <RequestAuditTrail requestId={id} />

        {fv.status_history !== false && req.status_history && req.status_history.length > 0 && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="font-semibold text-foreground mb-4 text-sm">Status History</h2>
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

        {(canHold || canResume || canCancel || canReopen) && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-4">
              <h2 className="font-semibold text-foreground">Actions</h2>
              <div>
                <Label htmlFor="hold-remarks">Remarks (optional)</Label>
                <Textarea
                  id="hold-remarks"
                  value={holdRemarks}
                  onChange={(e) => setHoldRemarks(e.target.value)}
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
                  <Button variant="destructive" onClick={() => doAction("cancel")} disabled={isPending} className="w-full sm:w-auto">
                    Cancel Request
                  </Button>
                )}
                {canReopen && (
                  <Button onClick={() => doAction("reopen")} disabled={isPending} className="w-full sm:w-auto">
                    Reopen
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </RoleGuard>
  );
}

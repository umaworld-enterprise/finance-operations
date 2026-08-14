"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useRequest, useHomApprove, useHomReject, useFieldVisibility, usePayment } from "@/hooks/useRequests";
import { DecisionDialog } from "@/components/hom/DecisionDialog";
import { SupplierDefaultHistory } from "@/components/forms/SupplierDefaultHistory";
import { TrancheList } from "@/components/tranches/TrancheList";
import { RequestAuditTrail } from "@/components/tranches/RequestAuditTrail";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ArrowLeft, Lock, FileQuestion, Check, X } from "lucide-react";
import Link from "next/link";

export default function HomRequestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: req, isLoading, isFetching } = useRequest(id);
  const { data: payment } = usePayment(id);
  const { data: fv = {} } = useFieldVisibility();
  const homApprove = useHomApprove();
  const homReject = useHomReject();
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  const canApprove = req?.current_status === "pending_hom_approval";
  const canReject  = req?.current_status === "pending_hom_approval";
  const actionBusy = homApprove.isPending || homReject.isPending || isFetching;

  const handleApprove = async (remarks: string) => {
    try {
      await homApprove.mutateAsync({ id, remarks });
      toast.success("Request approved — moved to payment queue.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to approve.");
    }
  };

  const handleReject = async (remarks: string) => {
    try {
      await homReject.mutateAsync({ id, remarks });
      toast.success("Request rejected.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to reject.");
    }
  };

  const field = (label: string, value: React.ReactNode) => (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-foreground">{value ?? "—"}</dd>
    </div>
  );

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
                <Link href="/hom">Back to dashboard</Link>
              </Button>
            }
          />
        </main>
      </>
    );
  }

  const snap = req.analytics_snapshot;

  return (
    <RoleGuard allowedRoles={["head_of_merchandiser", "super_admin"]}>
      <TopNav title={`Request ${req.request_number}`} />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
        <Link
          href="/hom"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
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

        {/* Request details */}
        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="text-sm font-semibold text-foreground mb-4">Request Details</h2>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-5">
              {field("Supplier", req.supplier.name)}
              {field("Customer", req.customer.name)}
              {field("Vertical", req.vertical?.name)}
              {field("Currency", req.currency)}
              {fv.deposit_amount !== false && field("Deposit Amount", formatCurrency(req.deposit_amount, req.currency ?? undefined))}
              {fv.deposit_percentage !== false && field("Deposit %", req.deposit_percentage != null ? `${req.deposit_percentage}%` : null)}
              {fv.total_supplier_invoice_amount !== false && field("Total Invoice Amount", formatCurrency(req.total_supplier_invoice_amount, req.currency ?? undefined))}
              {fv.exchange_rate !== false && req.exchange_rate != null && field("Exchange Rate", req.exchange_rate)}
              {req.sunshine_invoice_number && field("Sunshine Invoice #", req.sunshine_invoice_number)}
              {req.supplier_invoice_number && field("Supplier Proforma Invoice #", req.supplier_invoice_number)}
              {req.estimated_etd && field("Estimated ETD", formatDate(req.estimated_etd))}
              {req.payment_terms && field("Payment Terms", req.payment_terms)}
              {field("Submitted", formatDate(req.created_at))}
              {fv.creator_info !== false && field("Submitted By", req.creator ? `${req.creator.full_name} (${req.creator.email})` : req.submitter_email ?? null)}
              {payment?.ship_date && field("Ship Date", formatDate(payment.ship_date))}
              {fv.accounts_timestamp !== false && payment && field("Payment Last Updated", formatDate(payment.updated_at))}
            </dl>
            {req.remarks && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs font-medium text-muted-foreground mb-1">Merchandiser Remarks</p>
                <p className="text-sm text-foreground bg-muted/50 rounded-lg px-3 py-2">{req.remarks}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Analytics snapshot */}
        {snap && (fv.grace_etd !== false || fv.etd_grace_overdue_days !== false || fv.actual_etd_overdue_days !== false || fv.default_status !== false) && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="text-sm font-semibold text-foreground mb-4">Analytics</h2>
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-5">
                {fv.grace_etd !== false && field("Grace ETD", formatDate(snap.grace_etd))}
                {fv.etd_grace_overdue_days !== false && field("ETD Grace Overdue Days", snap.etd_grace_overdue_days != null ? `${snap.etd_grace_overdue_days}d` : null)}
                {fv.actual_etd_overdue_days !== false && field("Actual ETD Overdue Days", snap.actual_etd_overdue_days != null ? `${snap.actual_etd_overdue_days}d` : null)}
                {fv.cost_of_fund !== false && field("Cost of Fund", snap.cost_of_fund_amount != null ? formatCurrency(Number(snap.cost_of_fund_amount), req.currency ?? undefined) : null)}
                {fv.default_status !== false && field("Risk Status", snap.default_status)}
              </dl>
            </CardContent>
          </Card>
        )}

        {/* Advance Payment Tranches — the same particulars Accounts see,
            read-only (UAT Aug 2026, item 3). */}
        {(req.tranches?.length ?? 0) > 0 && (
          <Card>
            <CardContent className="p-5 md:p-6">
              <h2 className="text-sm font-semibold text-foreground mb-1">Advance Payment Tranches</h2>
              <p className="text-xs text-muted-foreground mb-4">
                Amounts, tentative dates and payment progress — exactly what the Accounts team works from.
              </p>
              <TrancheList
                requestId={id}
                tranches={req.tranches ?? []}
                currency={req.currency}
                mode="readonly"
              />
            </CardContent>
          </Card>
        )}

        {/* Supplier default track record — decisive context for approval */}
        <SupplierDefaultHistory
          supplierId={req.supplier.id}
          supplierName={req.supplier.name}
          currentRequest={{ id: req.id, deposit_amount: Number(req.deposit_amount), currency: req.currency }}
        />

        <RequestAuditTrail requestId={id} />

        {/* Status history */}
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

        {/* HOM actions */}
        {(canApprove || canReject) && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-4">
              <div>
                <h2 className="font-semibold text-foreground">Review Decision</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Approving moves this request to the accounts payment queue. Rejecting sends it back.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                {canApprove && (
                  <Button
                    onClick={() => setApproveOpen(true)}
                    disabled={actionBusy}
                    className="w-full sm:w-auto gap-1.5"
                  >
                    <Check className="h-4 w-4" /> Approve
                  </Button>
                )}
                {canReject && (
                  <Button
                    variant="destructive"
                    onClick={() => setRejectOpen(true)}
                    disabled={actionBusy}
                    className="w-full sm:w-auto gap-1.5"
                  >
                    <X className="h-4 w-4" /> Reject
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </main>

      <DecisionDialog
        open={approveOpen}
        title="Approve Request"
        description="Approving moves this request to the accounts payment queue. A reason is mandatory."
        placeholder="Reason for approval"
        confirmLabel="Confirm Approve"
        busy={actionBusy}
        onClose={() => setApproveOpen(false)}
        onConfirm={handleApprove}
      />
      <DecisionDialog
        open={rejectOpen}
        title="Reject Request"
        description="Rejecting is final for this request. A reason is mandatory — the merchandiser will be notified."
        placeholder="Reason for rejection"
        confirmLabel="Confirm Reject"
        destructive
        busy={actionBusy}
        onClose={() => setRejectOpen(false)}
        onConfirm={handleReject}
      />
    </RoleGuard>
  );
}

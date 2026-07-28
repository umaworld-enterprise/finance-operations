"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { useSuppliers } from "@/hooks/useMasters";
import { useAuth } from "@/hooks/useAuth";
import adjustmentService, { type CreateAdjustmentPayload } from "@/services/adjustmentService";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { PaymentTranche } from "@/types";
import { ArrowLeftRight } from "lucide-react";

const ADJUSTMENTS_KEY = ["adjustments"] as const;

function trancheOptionLabel(t: PaymentTranche, withBalance: boolean): string {
  const invoice = t.sunshine_invoice_number || t.supplier_invoice_number;
  const base = `${t.request_number}${invoice ? ` (${invoice})` : ""} — ${t.label}`;
  const amount = formatCurrency(
    withBalance ? Number(t.available_paid_balance ?? t.amount) : Number(t.amount),
    t.request_currency ?? undefined,
  );
  return `${base} · ${withBalance ? `available ${amount}` : amount}`;
}

export default function AdjustInvoicesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "accounts_team" || user?.role === "super_admin";
  const qc = useQueryClient();
  const { data: suppliers = [] } = useSuppliers();

  const [supplierId, setSupplierId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [destinationId, setDestinationId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const { data: options, isLoading: optionsLoading } = useQuery({
    queryKey: [...ADJUSTMENTS_KEY, "options", supplierId],
    queryFn: () => adjustmentService.supplierOptions(supplierId),
    enabled: !!supplierId,
    staleTime: 0,
  });

  const { data: history = [], isLoading: historyLoading } = useQuery({
    queryKey: [...ADJUSTMENTS_KEY, "history"],
    queryFn: () => adjustmentService.list(),
    staleTime: 60_000,
  });

  const createAdjustment = useMutation({
    mutationFn: (payload: CreateAdjustmentPayload) => adjustmentService.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...ADJUSTMENTS_KEY] });
    },
  });

  const source = options?.paid_sources.find((t) => t.id === sourceId);
  // The destination must be a tranche on ANOTHER invoice of the same supplier.
  const destinations = useMemo(
    () =>
      (options?.unpaid_destinations ?? []).filter(
        (t) => !source || t.deposit_request_id !== source.deposit_request_id,
      ),
    [options?.unpaid_destinations, source],
  );
  const destination = destinations.find((t) => t.id === destinationId);

  const amountNum = Number(amount) || 0;
  const available = Number(source?.available_paid_balance ?? 0);
  const amountError =
    amountNum > 0 && source && amountNum > available
      ? `Cannot exceed the remaining paid balance of ${formatCurrency(available, source.request_currency ?? undefined)}.`
      : null;
  const canSubmit = canWrite && source && destination && amountNum > 0 && !amountError;

  const doCreate = async () => {
    if (!canSubmit || !source || !destination) return;
    try {
      await createAdjustment.mutateAsync({
        source_tranche_id: source.id,
        destination_tranche_id: destination.id,
        amount: amountNum,
        reason: reason.trim() || undefined,
      });
      toast.success("Adjustment recorded — it is now traceable from both requests.");
      setSourceId("");
      setDestinationId("");
      setAmount("");
      setReason("");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to record the adjustment.");
    } finally {
      setConfirmOpen(false);
    }
  };

  const selectCls =
    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <RoleGuard allowedRoles={["accounts_team", "super_admin", "finance_admin"]}>
      <TopNav
        title="Adjust Invoices"
        subtitle="Reallocate value from a paid tranche to another invoice of the same supplier"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-5xl mx-auto w-full">
        {canWrite && (
          <Card>
            <CardContent className="p-5 md:p-6 space-y-4">
              <div>
                <h2 className="font-semibold text-foreground text-sm">New Adjustment</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  The paid tranche itself is never modified — each adjustment is a separate,
                  linked transaction against its remaining paid balance.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2">
                  <Label htmlFor="adj-supplier">Supplier</Label>
                  <select
                    id="adj-supplier"
                    value={supplierId}
                    onChange={(e) => {
                      setSupplierId(e.target.value);
                      setSourceId("");
                      setDestinationId("");
                    }}
                    className={`mt-1 ${selectCls}`}
                  >
                    <option value="">Select supplier</option>
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <Label htmlFor="adj-source">Source — paid tranche</Label>
                  <select
                    id="adj-source"
                    value={sourceId}
                    onChange={(e) => setSourceId(e.target.value)}
                    disabled={!supplierId || optionsLoading}
                    className={`mt-1 ${selectCls}`}
                  >
                    <option value="">
                      {optionsLoading
                        ? "Loading…"
                        : (options?.paid_sources.length ?? 0) === 0 && supplierId
                          ? "No paid tranches with remaining balance"
                          : "Select paid tranche"}
                    </option>
                    {options?.paid_sources.map((t) => (
                      <option key={t.id} value={t.id}>{trancheOptionLabel(t, true)}</option>
                    ))}
                  </select>
                  {source && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Paid {formatCurrency(Number(source.amount), source.request_currency ?? undefined)} · already
                      reallocated {formatCurrency(Number(source.adjusted_out_total ?? 0), source.request_currency ?? undefined)} · remaining{" "}
                      <span className="font-medium text-foreground">
                        {formatCurrency(available, source.request_currency ?? undefined)}
                      </span>
                    </p>
                  )}
                </div>

                <div>
                  <Label htmlFor="adj-destination">Destination — tranche on another invoice</Label>
                  <select
                    id="adj-destination"
                    value={destinationId}
                    onChange={(e) => setDestinationId(e.target.value)}
                    disabled={!supplierId || optionsLoading}
                    className={`mt-1 ${selectCls}`}
                  >
                    <option value="">
                      {destinations.length === 0 && supplierId && !optionsLoading
                        ? "No unpaid tranches on other invoices"
                        : "Select destination tranche"}
                    </option>
                    {destinations.map((t) => (
                      <option key={t.id} value={t.id}>{trancheOptionLabel(t, false)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <Label htmlFor="adj-amount">Amount</Label>
                  <input
                    id="adj-amount"
                    type="number"
                    step="0.01"
                    min="0"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className={`mt-1 ${selectCls}`}
                  />
                  {amountError && <p className="text-xs text-destructive mt-1">{amountError}</p>}
                </div>

                <div>
                  <Label htmlFor="adj-reason">Reason (optional)</Label>
                  <Textarea
                    id="adj-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={1}
                    className="mt-1"
                    placeholder="e.g. Order cancelled — advance applied to the replacement invoice."
                  />
                </div>
              </div>

              <Button onClick={() => setConfirmOpen(true)} disabled={!canSubmit || createAdjustment.isPending}>
                {createAdjustment.isPending ? "Recording…" : "Record Adjustment"}
              </Button>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="p-5 md:p-6">
            <h2 className="font-semibold text-foreground text-sm mb-4">Adjustment History</h2>
            {historyLoading ? (
              <Table>
                <TableBody>
                  <TableSkeleton rows={5} cols={5} />
                </TableBody>
              </Table>
            ) : history.length === 0 ? (
              <EmptyState
                icon={ArrowLeftRight}
                title="No adjustments yet"
                description="Reallocations from paid tranches to other invoices will appear here."
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Supplier</TableHead>
                      <TableHead>From</TableHead>
                      <TableHead>To</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead className="hidden md:table-cell">By</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(a.created_at)}
                        </TableCell>
                        <TableCell className="text-sm">{a.supplier_name ?? "—"}</TableCell>
                        <TableCell className="text-sm">
                          {a.source_request_id ? (
                            <Link href={`/accounts/${a.source_request_id}`} className="text-primary underline underline-offset-2">
                              {a.source_request_number}
                            </Link>
                          ) : a.source_request_number}
                          <span className="text-muted-foreground"> / {a.source_tranche_label}</span>
                        </TableCell>
                        <TableCell className="text-sm">
                          <span className="inline-flex items-center gap-1">
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            {a.destination_request_id ? (
                              <Link href={`/accounts/${a.destination_request_id}`} className="text-primary underline underline-offset-2">
                                {a.destination_request_number}
                              </Link>
                            ) : a.destination_request_number}
                            <span className="text-muted-foreground"> / {a.destination_tranche_label}</span>
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-sm">
                          {formatCurrency(Number(a.amount))}
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                          {a.performed_by_name ?? "—"}
                          {a.reason ? ` · ${a.reason}` : ""}
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

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Record this adjustment?"
        description={
          source && destination
            ? `${formatCurrency(amountNum, source.request_currency ?? undefined)} will be reallocated from ${source.request_number} / ${source.label} to ${destination.request_number} / ${destination.label}. The original paid tranche remains a preserved historical record.`
            : ""
        }
        confirmLabel="Yes, record adjustment"
        onConfirm={doCreate}
      />
    </RoleGuard>
  );
}

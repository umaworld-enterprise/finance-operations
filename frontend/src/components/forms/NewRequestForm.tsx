"use client";

// Supplier Advance Payment Request form. Extracted from /merchandiser/new so
// it can live inside the Merchandiser Queue as a collapsible section
// (Aug 2026 batch, item 2.2) — /merchandiser/new now just redirects here.

import { useEffect, useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { SupplierDefaultAlert } from "@/components/forms/SupplierDefaultAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { useVerticals, useCustomers, useSuppliers, useSupplierDefaultStatus } from "@/hooks/useMasters";
import { useCreateRequest } from "@/hooks/useRequests";
import requestService from "@/services/requestService";
import { currencyDisplayLabel, formatCurrency, todayLocalISO } from "@/lib/utils";
import type { DepositRequest } from "@/types";

type InvoiceField = "sunshine_invoice_number" | "supplier_invoice_number";

const INVOICE_FIELD_LABELS: Record<InvoiceField, string> = {
  sunshine_invoice_number: "Sunshine Invoice No.",
  supplier_invoice_number: "Supplier Proforma Invoice No.",
};

const trancheSchema = z.object({
  amount: z.coerce.number().positive("Must be positive"),
  tentative_payment_date: z.string().min(1, "Date is required"),
});

const schema = z
  .object({
    supplier_id: z.string().uuid("Select a supplier"),
    customer_id: z.string().uuid("Select a customer"),
    vertical_id: z.string().uuid("Select a vertical"),
    sunshine_invoice_number: z.string().optional(),
    supplier_invoice_number: z.string().optional(),
    currency: z.string().min(1),
    total_supplier_invoice_amount: z.coerce.number().positive("Must be positive"),
    estimated_etd: z.string().optional(),
    remarks: z.string().optional(),
    tranches: z.array(trancheSchema).min(1, "At least one tranche is required"),
  })
  .refine(
    (data) =>
      data.tranches.reduce((sum, t) => sum + (t.amount || 0), 0) <=
      data.total_supplier_invoice_amount,
    {
      message: "Total of tranche amounts cannot exceed the total supplier proforma invoice amount",
      path: ["tranches"],
    },
  );

type FormValues = z.infer<typeof schema>;

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"];

const DEFAULT_VALUES = {
  tranches: [{ amount: undefined as unknown as number, tentative_payment_date: "" }],
};

// 1 → "I", 2 → "II", … for tranche labels.
function roman(n: number): string {
  const map: [number, string][] = [
    [1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"],
    [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"],
  ];
  let out = "";
  for (const [v, s] of map) {
    while (n >= v) {
      out += s;
      n -= v;
    }
  }
  return out;
}

interface Props {
  onSuccess?: (created: DepositRequest) => void;
  onCancel?: () => void;
}

export function NewRequestForm({ onSuccess, onCancel }: Props) {
  const { data: verticals = [] } = useVerticals();
  const { data: customers = [] } = useCustomers();
  const { data: suppliers = [] } = useSuppliers();
  const createRequest = useCreateRequest();

  const [overrideFlaggedSupplier, setOverrideFlaggedSupplier] = useState(false);

  // Duplicate invoice validation: inline warnings on blur, blocking popup on
  // submit. The server re-validates on create either way.
  const [dupNotices, setDupNotices] = useState<Partial<Record<InvoiceField, string | null>>>({});
  const [dupModal, setDupModal] = useState<string[] | null>(null);

  const findDuplicate = async (field: InvoiceField, raw: string | undefined): Promise<string | null> => {
    const value = raw?.trim();
    if (!value) return null;
    try {
      const res = await requestService.checkInvoiceNumber(field, value);
      return res.duplicate ? (res.request_number ?? "another request") : null;
    } catch {
      // A failed pre-check never blocks — creation re-validates server-side.
      return null;
    }
  };

  const onInvoiceBlur = async (field: InvoiceField, value: string) => {
    const conflict = await findDuplicate(field, value);
    setDupNotices((prev) => ({
      ...prev,
      [field]: conflict
        ? `${INVOICE_FIELD_LABELS[field]} "${value.trim()}" is already used by request ${conflict}.`
        : null,
    }));
  };

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      tranches: [{ amount: undefined as unknown as number, tentative_payment_date: todayLocalISO() }],
    },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "tranches" });

  const selectedSupplierId = watch("supplier_id");
  const { data: defaultStatus } = useSupplierDefaultStatus(selectedSupplierId || null);

  // Reset override whenever the supplier changes
  useEffect(() => {
    setOverrideFlaggedSupplier(false);
  }, [selectedSupplierId]);

  const isBlocked = defaultStatus?.is_defaulted === true && !overrideFlaggedSupplier;

  const currency = watch("currency");
  const totalInvoiceAmount = Number(watch("total_supplier_invoice_amount")) || 0;
  const watchedTranches = watch("tranches");
  const trancheTotal = (watchedTranches ?? []).reduce((sum, t) => sum + (Number(t?.amount) || 0), 0);

  // Find the selected supplier to check for fixed deposit amount
  const selectedSupplier = suppliers.find((s) => s.id === selectedSupplierId);
  const hasFixedDeposit = selectedSupplier?.fixed_deposit_amount != null;

  // Fixed-deposit suppliers: prefill Tranche I with the fixed advance amount.
  useEffect(() => {
    if (hasFixedDeposit && selectedSupplier?.fixed_deposit_amount != null) {
      setValue("tranches.0.amount", selectedSupplier.fixed_deposit_amount);
    }
  }, [hasFixedDeposit, selectedSupplier?.fixed_deposit_amount, setValue]);

  const clearForm = () => {
    reset({
      ...DEFAULT_VALUES,
      tranches: [{ amount: undefined as unknown as number, tentative_payment_date: todayLocalISO() }],
    });
    setDupNotices({});
    setOverrideFlaggedSupplier(false);
  };

  const onSubmit = async (data: FormValues) => {
    if (isBlocked) return;

    // Duplicate invoice numbers block submission with a popup.
    const dupMessages: string[] = [];
    for (const field of ["sunshine_invoice_number", "supplier_invoice_number"] as InvoiceField[]) {
      const value = data[field]?.trim();
      if (!value) continue;
      const conflict = await findDuplicate(field, value);
      if (conflict) {
        dupMessages.push(
          `${INVOICE_FIELD_LABELS[field]} "${value}" is already used by request ${conflict}.`,
        );
      }
    }
    if (dupMessages.length > 0) {
      setDupModal(dupMessages);
      return;
    }

    try {
      const created = await createRequest.mutateAsync({ ...data, override_flagged_supplier: overrideFlaggedSupplier });
      toast.success(
        created.current_status === "pending_hom_approval"
          ? "Request sent to the Head of Merchandiser for approval."
          : "Request submitted.",
      );
      clearForm();
      onSuccess?.(created);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to submit request.");
    }
  };

  return (
    <>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {defaultStatus && (
          <SupplierDefaultAlert
            status={defaultStatus}
            onContinue={() => setOverrideFlaggedSupplier(true)}
            onWithdraw={() => {
              setValue("supplier_id", "");
              setOverrideFlaggedSupplier(false);
            }}
          />
        )}
        {overrideFlaggedSupplier && (
          <div className="rounded-lg bg-amber-50 border border-amber-300 text-amber-800 p-3 text-sm">
            This request will be routed to the Head of Merchandiser for approval before going to Accounts.
          </div>
        )}

        <Card>
          <CardContent className="p-5 md:p-6 space-y-5">
            <h2 className="font-semibold text-foreground">Request Details</h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field
                label="Supplier"
                required
                tooltip="The supplier who will receive the advance payment. If the supplier is on the defaulted list, you cannot submit a request."
                error={errors.supplier_id?.message}
                variant="select"
                {...register("supplier_id")}
              >
                <option value="">Select supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </Field>

              <Field
                label="Customer"
                required
                tooltip="The customer this purchase is being made for."
                error={errors.customer_id?.message}
                variant="select"
                {...register("customer_id")}
              >
                <option value="">Select customer</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Field>

              <Field
                label="Vertical / Category"
                required
                tooltip="The product category this advance payment relates to (e.g. Frozen, Hardware)."
                error={errors.vertical_id?.message}
                variant="select"
                {...register("vertical_id")}
              >
                <option value="">Select vertical</option>
                {verticals.map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </Field>

              <Field
                label="Currency"
                required
                tooltip="The currency of the advance payment amount. Use OTHER if your currency is not listed."
                error={errors.currency?.message}
                variant="select"
                {...register("currency")}
              >
                <option value="">Select currency</option>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{currencyDisplayLabel(c)}</option>
                ))}
              </Field>

              <Field
                label="Sunshine Invoice No."
                tooltip="Your internal invoice number at Sunshine. A number already used by a live request is rejected."
                error={errors.sunshine_invoice_number?.message || dupNotices.sunshine_invoice_number || undefined}
                type="text"
                placeholder="INV-00123"
                {...register("sunshine_invoice_number", {
                  onBlur: (e) => void onInvoiceBlur("sunshine_invoice_number", e.target.value),
                })}
              />

              <Field
                label="Supplier Proforma Invoice No."
                tooltip="The proforma invoice number from the supplier's document. A number already used by a live request is rejected."
                error={dupNotices.supplier_invoice_number || undefined}
                type="text"
                {...register("supplier_invoice_number", {
                  onBlur: (e) => void onInvoiceBlur("supplier_invoice_number", e.target.value),
                })}
              />

              <Field
                label="Total Supplier Proforma Invoice Amount"
                required
                tooltip="The full proforma invoice total from the supplier. Tranche percentages are calculated against this amount."
                error={errors.total_supplier_invoice_amount?.message}
                type="number"
                step="0.01"
                {...register("total_supplier_invoice_amount")}
              />

              <Field
                label="Estimated ETD"
                tooltip="Estimated Time of Departure — when goods are expected to leave the origin port/warehouse."
                error={errors.estimated_etd?.message}
                type="date"
                {...register("estimated_etd")}
              />
            </div>

            {/* Advance Payment Tranches — one or more tranches, each with an
                amount and a tentative payment date. The % of invoice is
                system-calculated and read-only. Disabled until a currency is
                selected so tranche amounts are always entered in a known
                deposit currency. */}
            <fieldset disabled={!currency} className="space-y-3 disabled:opacity-60">
              <div>
                <label className="text-sm font-medium text-foreground">Advance Payment Tranches</label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Split the advance into one or more tranches. The percentage of the
                  proforma invoice is calculated automatically.
                </p>
                {!currency && (
                  <p className="text-xs text-amber-700 mt-1">
                    Select a currency above to enter tranche amounts.
                  </p>
                )}
              </div>

              {fields.map((f, i) => (
                <div key={f.id} className="rounded-lg border border-border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-foreground">Deposit - Tranche {roman(i + 1)}</span>
                    {fields.length > 1 && (
                      <button
                        type="button"
                        onClick={() => remove(i)}
                        aria-label={`Remove Deposit - Tranche ${roman(i + 1)}`}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-muted transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="space-y-1.5">
                      <p className="text-xs text-muted-foreground">
                        {currency ? `Amount (${currencyDisplayLabel(currency)})` : "Amount"}
                      </p>
                      <Field
                        error={errors.tranches?.[i]?.amount?.message}
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        tooltip={
                          i === 0 && hasFixedDeposit
                            ? `This supplier has a fixed advance amount of ${formatCurrency(selectedSupplier!.fixed_deposit_amount!, currency)}.`
                            : "The advance amount for this tranche."
                        }
                        {...register(`tranches.${i}.amount`)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs text-muted-foreground">% of invoice (auto)</p>
                      <input
                        type="text"
                        value={
                          totalInvoiceAmount > 0 && Number(watchedTranches?.[i]?.amount) > 0
                            ? `${((Number(watchedTranches[i].amount) / totalInvoiceAmount) * 100).toFixed(2)}%`
                            : "—"
                        }
                        readOnly
                        tabIndex={-1}
                        className="flex h-9 w-full rounded-md border border-input bg-muted px-3 py-1 text-sm opacity-70 cursor-not-allowed"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs text-muted-foreground">
                        Tentative payment date<span className="text-foreground ml-0.5" aria-hidden="true">*</span>
                      </p>
                      <Field
                        required
                        error={errors.tranches?.[i]?.tentative_payment_date?.message}
                        type="date"
                        {...register(`tranches.${i}.tentative_payment_date`)}
                      />
                    </div>
                  </div>
                </div>
              ))}

              {errors.tranches?.root?.message && (
                <p className="text-xs text-destructive">{errors.tranches.root.message}</p>
              )}
              {typeof errors.tranches?.message === "string" && (
                <p className="text-xs text-destructive">{errors.tranches.message}</p>
              )}

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => append({ amount: undefined as unknown as number, tentative_payment_date: todayLocalISO() })}
                >
                  <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Tranche {roman(fields.length + 1)}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Total advance: <span className="font-medium text-foreground">{formatCurrency(trancheTotal, currency)}</span>
                  {totalInvoiceAmount > 0 && (
                    <> ({((trancheTotal / totalInvoiceAmount) * 100).toFixed(2)}% of invoice)</>
                  )}
                </p>
              </div>
            </fieldset>

            {hasFixedDeposit && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                This supplier has a fixed advance amount of {formatCurrency(selectedSupplier!.fixed_deposit_amount!, currency)} — Tranche I has been pre-filled with it.
              </p>
            )}

            <Field
              label="Remarks"
              tooltip="Any additional notes for the Accounts team reviewing this request."
              variant="textarea"
              rows={3}
              {...register("remarks")}
            />
          </CardContent>
        </Card>

        <div className="flex flex-col sm:flex-row justify-end gap-3">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                clearForm();
                onCancel();
              }}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
          )}
          <Button
            type="submit"
            disabled={isBlocked || isSubmitting}
            className="w-full sm:w-auto"
          >
            {isSubmitting ? "Submitting…" : "Submit Request"}
          </Button>
        </div>
      </form>

      {/* Duplicate invoice popup — blocks submission until the number changes */}
      {dupModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card rounded-xl border border-border shadow-lg p-6 w-full max-w-md space-y-4">
            <h3 className="font-semibold text-foreground">Duplicate Deposit Request</h3>
            <div className="space-y-2">
              {dupModal.map((msg) => (
                <p key={msg} className="text-sm text-foreground">{msg}</p>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              A deposit request already exists for this invoice number. Change the
              number, or locate the existing request instead of raising a new one.
            </p>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setDupModal(null)}>
                Back to form
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

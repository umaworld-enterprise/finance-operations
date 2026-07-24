"use client";

import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { SupplierDefaultAlert } from "@/components/forms/SupplierDefaultAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { useVerticals, useCustomers, useSuppliers, useSupplierDefaultStatus, usePaymentTerms } from "@/hooks/useMasters";
import { Combobox } from "@/components/ui/Combobox";
import { useCreateRequest } from "@/hooks/useRequests";
import { formatCurrency } from "@/lib/utils";


const schema = z.object({
  supplier_id: z.string().uuid("Select a supplier"),
  customer_id: z.string().uuid("Select a customer"),
  vertical_id: z.string().uuid("Select a vertical"),
  sunshine_invoice_number: z.string().optional(),
  supplier_invoice_number: z.string().optional(),
  currency: z.string().min(1),
  deposit_amount: z.coerce.number().positive("Must be positive"),
  deposit_percentage: z.coerce.number().min(0).max(100).optional(),
  total_supplier_invoice_amount: z.coerce.number().positive("Must be positive"),
  estimated_etd: z.string().optional(),
  payment_terms: z.string().optional(),
  remarks: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"];

export default function NewRequestPage() {
  const router = useRouter();
  const { data: verticals = [] } = useVerticals();
  const { data: customers = [] } = useCustomers();
  const { data: suppliers = [] } = useSuppliers();
  const { data: paymentTerms = [] } = usePaymentTerms();
  const createRequest = useCreateRequest();

  const [overrideFlaggedSupplier, setOverrideFlaggedSupplier] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const selectedSupplierId = watch("supplier_id");
  const { data: defaultStatus } = useSupplierDefaultStatus(selectedSupplierId || null);

  // Reset override whenever the supplier changes
  useEffect(() => {
    setOverrideFlaggedSupplier(false);
  }, [selectedSupplierId]);

  const isBlocked = defaultStatus?.is_defaulted === true && !overrideFlaggedSupplier;

  const currency = watch("currency");

  // Find the selected supplier to check for fixed deposit amount
  const selectedSupplier = suppliers.find((s) => s.id === selectedSupplierId);
  const hasFixedDeposit = selectedSupplier?.fixed_deposit_amount != null;

  // Auto-fill deposit amount: fixed per supplier, or percentage-calculated
  useEffect(() => {
    if (hasFixedDeposit && selectedSupplier?.fixed_deposit_amount != null) {
      setValue("deposit_amount", selectedSupplier.fixed_deposit_amount);
      setValue("deposit_percentage", undefined);
    }
  }, [hasFixedDeposit, selectedSupplier?.fixed_deposit_amount, setValue]);

  const onSubmit = async (data: FormValues) => {
    if (isBlocked) return;
    try {
      await createRequest.mutateAsync({ ...data, override_flagged_supplier: overrideFlaggedSupplier });
      toast.success("Request submitted successfully.");
      router.push("/merchandiser");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to submit request.");
    }
  };

  return (
    <RoleGuard allowedRoles={["merchandiser", "super_admin"]}>
      <TopNav title="New Deposit Request" />
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <div className="max-w-3xl mx-auto">
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
                This request will be routed to the Head of Merchandising for approval before going to Accounts.
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
                    tooltip="The product category this deposit relates to (e.g. Frozen, Hardware)."
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
                    tooltip="The currency of the deposit amount. Use OTHER if your currency is not listed."
                    error={errors.currency?.message}
                    variant="select"
                    {...register("currency")}
                  >
                    <option value="">Select currency</option>
                    {CURRENCIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </Field>

                  <Field
                    label="Sunshine Invoice Number"
                    tooltip="Your internal invoice number at Sunshine."
                    error={errors.sunshine_invoice_number?.message}
                    type="text"
                    placeholder="INV-00123"
                    {...register("sunshine_invoice_number")}
                  />

                  <Field
                    label="Supplier Invoice Number"
                    tooltip="The invoice number from the supplier's document."
                    type="text"
                    {...register("supplier_invoice_number")}
                  />

                  <Field
                    label="Total Supplier Invoice Amount"
                    required
                    tooltip="The full invoice total from the supplier."
                    error={errors.total_supplier_invoice_amount?.message}
                    type="number"
                    step="0.01"
                    {...register("total_supplier_invoice_amount")}
                  />

                  <Field
                    label="Deposit Amount"
                    required
                    tooltip={
                      hasFixedDeposit
                        ? `This supplier has a fixed deposit amount of ${formatCurrency(selectedSupplier!.fixed_deposit_amount!, currency || "USD")}.`
                        : "The actual advance amount to be paid."
                    }
                    error={errors.deposit_amount?.message}
                    type="number"
                    step="0.01"
                    readOnly={hasFixedDeposit}
                    className={hasFixedDeposit ? "opacity-70" : ""}
                    {...register("deposit_amount")}
                  />

                  <Field
                    label="Estimated ETD"
                    tooltip="Estimated Time of Departure — when goods are expected to leave the origin port/warehouse."
                    error={errors.estimated_etd?.message}
                    type="date"
                    {...register("estimated_etd")}
                  />
                </div>

                {/* Payment Terms — 3-field group: Deposit %, Balance % (auto), Balance Due */}
                {!hasFixedDeposit && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">Payment Terms</label>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground">Deposit (%)</p>
                        <Field
                          error={errors.deposit_percentage?.message}
                          type="number"
                          step="0.01"
                          min="0"
                          max="100"
                          placeholder="e.g. 30"
                          tooltip="Percentage of the invoice paid upfront as deposit."
                          {...register("deposit_percentage")}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground">Balance (%)</p>
                        <input
                          type="number"
                          value={100 - (Number(watch("deposit_percentage")) || 0)}
                          readOnly
                          tabIndex={-1}
                          className="flex h-9 w-full rounded-md border border-input bg-muted px-3 py-1 text-sm opacity-70 cursor-not-allowed"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground">Balance Due</p>
                        <Controller
                          name="payment_terms"
                          control={control}
                          render={({ field }) => (
                            <Combobox
                              value={field.value ?? ""}
                              onChange={field.onChange}
                              options={paymentTerms.map((t) => t.label)}
                              placeholder="Select…"
                              allowFreeText={true}
                              aria-invalid={!!errors.payment_terms}
                            />
                          )}
                        />
                        {errors.payment_terms && (
                          <p className="text-xs text-destructive">{errors.payment_terms.message}</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {hasFixedDeposit && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                    This supplier has a fixed deposit amount of {formatCurrency(selectedSupplier!.fixed_deposit_amount!, currency || "USD")} — the deposit percentage field is not applicable.
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
              <Button
                type="button"
                variant="outline"
                onClick={() => router.back()}
                className="w-full sm:w-auto"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isBlocked || isSubmitting}
                className="w-full sm:w-auto"
              >
                {isSubmitting ? "Submitting…" : "Submit Request"}
              </Button>
            </div>
          </form>
        </div>
      </main>
    </RoleGuard>
  );
}

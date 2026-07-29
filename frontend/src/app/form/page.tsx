"use client";

import { useEffect, useRef, useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import Image from "next/image";
import { CheckCircle2, Loader2, AlertCircle, Plus, Trash2 } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── Types ─────────────────────────────────────────────────────────────────────

interface MasterItem { id: string; name: string }
interface SupplierItem { id: string; name: string; fixed_deposit_amount: number | null; is_flagged: boolean }
interface Masters {
  verticals: MasterItem[];
  customers: MasterItem[];
  suppliers: SupplierItem[];
  currencies: string[];
}

interface FieldConfig {
  visible: boolean;
  required: boolean;
  label: string;
}

type FormConfig = Record<string, FieldConfig>;

// ── All possible fields in render order ───────────────────────────────────────

// payment_terms / deposit_percentage / deposit_amount were retired in favour
// of Advance Payment Tranches (always shown — every request needs at least one).
const FIELD_ORDER = [
  "supplier_id",
  "customer_id",
  "vertical_id",
  "sunshine_invoice_number",
  "supplier_invoice_number",
  "currency",
  "total_supplier_invoice_amount",
  "estimated_etd",
  "remarks",
] as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function isVisible(cfg: FormConfig, key: string): boolean {
  return cfg[key]?.visible !== false;
}

function isRequired(cfg: FormConfig, key: string): boolean {
  return cfg[key]?.required === true;
}

function label(cfg: FormConfig, key: string, fallback: string): string {
  return cfg[key]?.label || fallback;
}

function currencyLabel(c: string) {
  return c === "CNY" ? "CNY (RMB)" : c;
}

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

function Field({
  label: lbl, error, required, children,
}: {
  label: string; error?: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-gray-700">
        {lbl}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {error && (
        <p className="text-xs text-red-600 flex items-center gap-1">
          <AlertCircle className="h-3 w-3" />{error}
        </p>
      )}
    </div>
  );
}

// text-base (16px) prevents iOS Safari from auto-zooming when an input is focused.
// Any font-size below 16px triggers the zoom — do NOT change back to text-sm.
const inputCls = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-base text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 disabled:bg-gray-50 disabled:text-gray-500 touch-manipulation";

// ── Form values type ──────────────────────────────────────────────────────────

type TrancheRow = {
  amount: string;
  tentative_payment_date: string;
};

type FormValues = {
  submitter_email: string;
  supplier_id: string;
  customer_id: string;
  vertical_id: string;
  currency: string;
  sunshine_invoice_number: string;
  supplier_invoice_number: string;
  total_supplier_invoice_amount: string;
  estimated_etd?: string;
  remarks: string;
  tranches: TrancheRow[];
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function PublicFormPage() {
  const [masters, setMasters] = useState<Masters | null>(null);
  const [config, setConfig] = useState<FormConfig>({});
  const [loadError, setLoadError] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showFlagConfirm, setShowFlagConfirm] = useState(false);
  const overrideFlagRef = useRef(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors },
    setError,
  } = useForm<FormValues>({
    mode: "onBlur",
    defaultValues: { tranches: [{ amount: "", tentative_payment_date: "" }] },
  });
  const { fields: trancheFields, append: appendTranche, remove: removeTranche } = useFieldArray({
    control,
    name: "tranches",
  });

  const selectedSupplierId = watch("supplier_id");
  const watchedTranches = watch("tranches");
  const totalInvoiceAmount = Number(watch("total_supplier_invoice_amount")) || 0;
  const trancheTotal = (watchedTranches ?? []).reduce(
    (sum, t) => sum + (Number(t?.amount) || 0),
    0,
  );

  // Find selected supplier to check for fixed deposit amount and flag status
  const selectedSupplier = masters?.suppliers.find((s) => s.id === selectedSupplierId);
  const hasFixedDeposit = selectedSupplier?.fixed_deposit_amount != null;
  const isFlaggedSupplier = selectedSupplier?.is_flagged ?? false;

  // Reset override when supplier changes
  useEffect(() => {
    overrideFlagRef.current = false;
  }, [selectedSupplierId]);

  // Fixed-deposit suppliers: prefill Tranche I with the fixed advance amount.
  useEffect(() => {
    if (hasFixedDeposit && selectedSupplier?.fixed_deposit_amount != null) {
      setValue("tranches.0.amount", String(selectedSupplier.fixed_deposit_amount));
    }
  }, [hasFixedDeposit, selectedSupplier?.fixed_deposit_amount, setValue]);

  // Load masters and config in parallel
  useEffect(() => {
    Promise.all([
      fetch(`${API}/public/masters`).then((r) => r.json()),
      fetch(`${API}/public/form-config`).then((r) => r.json()).catch(() => ({})),
    ])
      .then(([m, c]) => {
        setMasters(m);
        setConfig(c ?? {});
      })
      .catch(() => setLoadError(true));
  }, []);

  async function onSubmit(values: FormValues) {
    // Run config-driven required checks (since we're not using Zod here)
    let hasError = false;
    for (const key of FIELD_ORDER) {
      if (isVisible(config, key) && isRequired(config, key)) {
        const val = values[key];
        if (!val || val.trim() === "") {
          setError(key as keyof FormValues, { message: `${label(config, key, key)} is required` });
          hasError = true;
        }
      }
    }
    if (!values.submitter_email?.trim()) {
      setError("submitter_email", { message: "Email is required" });
      hasError = true;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.submitter_email)) {
      setError("submitter_email", { message: "Enter a valid email address" });
      hasError = true;
    }

    // Advance Payment Tranches — always required (at least one).
    values.tranches.forEach((t, i) => {
      if (!t.amount || Number(t.amount) <= 0) {
        setError(`tranches.${i}.amount`, { message: "Enter a positive amount" });
        hasError = true;
      }
      if (!t.tentative_payment_date) {
        setError(`tranches.${i}.tentative_payment_date`, { message: "Date is required" });
        hasError = true;
      }
    });
    const total = values.tranches.reduce((s, t) => s + (Number(t.amount) || 0), 0);
    const invoiceTotal = Number(values.total_supplier_invoice_amount) || 0;
    if (invoiceTotal > 0 && total > invoiceTotal) {
      setError("tranches.0.amount", {
        message: "Total of tranche amounts cannot exceed the total supplier proforma invoice amount",
      });
      hasError = true;
    }
    if (hasError) return;

    setServerError(null);
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        submitter_email: values.submitter_email,
        override_flagged_supplier: overrideFlagRef.current,
      };

      // Include estimated_etd when provided
      if (values.estimated_etd?.trim()) body.estimated_etd = values.estimated_etd;

      // Advance Payment Tranches — the deposit amount is derived server-side
      // as their sum; the % of invoice is always system-calculated.
      body.tranches = values.tranches.map((t) => ({
        amount: parseFloat(t.amount),
        tentative_payment_date: t.tentative_payment_date,
      }));

      // Include remaining config-driven visible fields
      for (const key of FIELD_ORDER) {
        if (key === "estimated_etd") continue; // already handled above
        if (!isVisible(config, key)) continue;
        const v = values[key];
        if (key === "total_supplier_invoice_amount") {
          body[key] = parseFloat(v ?? "") || 0;
        } else {
          body[key] = v || null;
        }
      }

      const res = await fetch(`${API}/public/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      let data: Record<string, unknown> = {};
      try { data = await res.json(); } catch { /* non-JSON response */ }
      if (!res.ok) {
        // Parse FastAPI validation errors (detail is an array) or custom error messages
        const detail = data.detail;
        const msg = data.message
          ?? (Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg ?? String(d)).join("; ") : detail)
          ?? "Something went wrong. Please try again.";
        setServerError(typeof msg === "string" ? msg : "Something went wrong. Please try again.");
        return;
      }
      setSubmitted(data.request_number as string);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : String(e);
      const isNetworkError = errMsg === "Failed to fetch" || errMsg.toLowerCase().includes("network");
      setServerError(
        isNetworkError
          ? "Could not reach the server. Please check your connection and try again in a moment."
          : `Submission failed — ${errMsg}. Please contact support.`
      );
    } finally {
      setSubmitting(false);
    }
  }

  // ── Success ─────────────────────────────────────────────────────────────────
  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-gray-50">
        <div className="w-full max-w-md bg-white rounded-2xl border border-gray-200 shadow-sm p-10 text-center">
          <CheckCircle2 className="h-14 w-14 text-gray-900 mx-auto mb-5" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Request Submitted</h1>
          <p className="text-gray-600 text-sm mb-6">
            Your Supplier Advance Payment Request has been received and will be reviewed by the accounts team.
          </p>
          <div className="bg-gray-50 rounded-xl border border-gray-200 px-6 py-4 mb-6">
            <p className="text-xs text-gray-500 mb-1">Request Number</p>
            <p className="text-2xl font-mono font-bold text-gray-900">{submitted}</p>
          </div>
          <p className="text-xs text-gray-400">Keep this number for your records.</p>
        </div>
      </div>
    );
  }

  // ── Load error ──────────────────────────────────────────────────────────────
  if (loadError) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="text-center">
          <AlertCircle className="h-10 w-10 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-600">Unable to load the form. Please try again later.</p>
        </div>
      </div>
    );
  }

  if (!masters) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  // ── Render fields ────────────────────────────────────────────────────────────

  const show = (key: string) => isVisible(config, key);
  const req = (key: string) => isRequired(config, key);
  const lbl = (key: string, fallback: string) => label(config, key, fallback);

  return (
    <>
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="mx-auto w-full max-w-xl">

        {/* Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="bg-white border border-gray-200 p-3 rounded-xl mb-3 shadow-sm">
            <Image src="/logo.png" alt="Sunshine" width={36} height={36} className="h-9 w-9 object-contain" />
          </div>
          <h1 className="text-xl font-bold text-gray-900">Sunshine — Supplier Advance Payment Request</h1>
          <p className="text-sm text-gray-500 mt-1 text-center">
            Fill in all required fields and submit. The finance team will review your request.
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 space-y-5">

          {/* Email — always shown */}
          <Field label="Your Email" required error={errors.submitter_email?.message}>
            <input
              {...register("submitter_email")}
              type="email"
              placeholder="your.email@example.com"
              className={inputCls}
            />
          </Field>

          {/* Parties group */}
          {(show("supplier_id") || show("customer_id") || show("vertical_id")) && <hr className="border-gray-100" />}

          {show("supplier_id") && (
            <Field label={lbl("supplier_id", "Select Supplier")} required={req("supplier_id")} error={errors.supplier_id?.message}>
              <select {...register("supplier_id")} className={inputCls} defaultValue="">
                <option value="" disabled>Choose supplier…</option>
                {masters.suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </Field>
          )}

          {isFlaggedSupplier && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" />
              <span>
                <strong>{selectedSupplier?.name}</strong> is on the defaulted supplier list.
                Fill in the form and use <strong>Proceed</strong> at the bottom to submit for Head of Merchandiser approval.
              </span>
            </div>
          )}

          {show("customer_id") && (
            <Field label={lbl("customer_id", "Select Customer")} required={req("customer_id")} error={errors.customer_id?.message}>
              <select {...register("customer_id")} className={inputCls} defaultValue="">
                <option value="" disabled>Choose customer…</option>
                {masters.customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </Field>
          )}

          {show("vertical_id") && (
            <Field label={lbl("vertical_id", "Vertical / Category")} required={req("vertical_id")} error={errors.vertical_id?.message}>
              <select {...register("vertical_id")} className={inputCls} defaultValue="">
                <option value="" disabled>Choose category…</option>
                {masters.verticals.map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </Field>
          )}

          {/* Invoice numbers */}
          {(show("sunshine_invoice_number") || show("supplier_invoice_number")) && <hr className="border-gray-100" />}
          {(show("sunshine_invoice_number") || show("supplier_invoice_number")) && (
            <div className="grid grid-cols-2 gap-4">
              {show("sunshine_invoice_number") && (
                <Field label={lbl("sunshine_invoice_number", "Sunshine Invoice No.")} required={req("sunshine_invoice_number")} error={errors.sunshine_invoice_number?.message}>
                  <input {...register("sunshine_invoice_number")} type="text" placeholder="INV-XXXXX" className={inputCls} />
                </Field>
              )}
              {show("supplier_invoice_number") && (
                <Field label={lbl("supplier_invoice_number", "Supplier Invoice No.")} required={req("supplier_invoice_number")} error={errors.supplier_invoice_number?.message}>
                  <input {...register("supplier_invoice_number")} type="text" placeholder="SUP-XXXXX" className={inputCls} />
                </Field>
              )}
            </div>
          )}

          {/* Financials — the tranche section always renders */}
          <hr className="border-gray-100" />

          {show("currency") && (
            <Field label={lbl("currency", "Currency of Advance Payment")} required={req("currency")} error={errors.currency?.message}>
              <select {...register("currency")} className={inputCls} defaultValue="">
                <option value="" disabled>Choose currency…</option>
                {masters.currencies.map((c) => (
                  <option key={c} value={c}>{currencyLabel(c)}</option>
                ))}
              </select>
            </Field>
          )}

          {show("total_supplier_invoice_amount") && (
            <Field label={lbl("total_supplier_invoice_amount", "Total Supplier Proforma Invoice Amount")} required={req("total_supplier_invoice_amount")} error={errors.total_supplier_invoice_amount?.message}>
              <input {...register("total_supplier_invoice_amount")} type="number" step="0.01" min="0" placeholder="0.00" className={inputCls} />
            </Field>
          )}

          {/* Advance Payment Tranches — one or more tranches, each with an
              amount and a tentative payment date. % of invoice is calculated. */}
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Advance Payment Tranches<span className="text-red-500 ml-0.5">*</span>
              </label>
              <p className="text-xs text-gray-500 mt-0.5">
                Split the advance into one or more tranches. The percentage of the
                proforma invoice is calculated automatically.
              </p>
            </div>

            {trancheFields.map((f, i) => (
              <div key={f.id} className="rounded-xl border border-gray-200 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-900">Tranche {roman(i + 1)}</span>
                  {trancheFields.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeTranche(i)}
                      aria-label={`Remove Tranche ${roman(i + 1)}`}
                      className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-gray-50 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <label className="block text-xs text-gray-500">Amount</label>
                    <input
                      {...register(`tranches.${i}.amount`)}
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      className={inputCls}
                    />
                    {errors.tranches?.[i]?.amount && (
                      <p className="text-xs text-red-600 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" />{errors.tranches[i]?.amount?.message}
                      </p>
                    )}
                  </div>
                  <div className="space-y-1">
                    <label className="block text-xs text-gray-500">% of invoice (auto)</label>
                    <input
                      type="text"
                      value={
                        totalInvoiceAmount > 0 && Number(watchedTranches?.[i]?.amount) > 0
                          ? `${((Number(watchedTranches[i].amount) / totalInvoiceAmount) * 100).toFixed(2)}%`
                          : "—"
                      }
                      readOnly
                      tabIndex={-1}
                      className={inputCls + " opacity-70 cursor-not-allowed"}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-xs text-gray-500">Tentative payment date</label>
                    <input
                      {...register(`tranches.${i}.tentative_payment_date`)}
                      type="date"
                      className={inputCls}
                    />
                    {errors.tranches?.[i]?.tentative_payment_date && (
                      <p className="text-xs text-red-600 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" />{errors.tranches[i]?.tentative_payment_date?.message}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => appendTranche({ amount: "", tentative_payment_date: "" })}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-xl px-3 py-2 hover:bg-gray-50 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" /> Add Tranche {roman(trancheFields.length + 1)}
              </button>
              <p className="text-xs text-gray-500">
                Total advance:{" "}
                <span className="font-medium text-gray-900">
                  {trancheTotal.toFixed(2)} {watch("currency") || ""}
                </span>
                {totalInvoiceAmount > 0 && (
                  <> ({((trancheTotal / totalInvoiceAmount) * 100).toFixed(2)}% of invoice)</>
                )}
              </p>
            </div>
          </div>

          {hasFixedDeposit && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              This supplier has a fixed advance amount of {selectedSupplier?.fixed_deposit_amount} {watch("currency") || ""} — Tranche I has been pre-filled with it.
            </p>
          )}

          {/* Estimated ETD */}
          {show("estimated_etd") && <hr className="border-gray-100" />}
          {show("estimated_etd") && (
            <Field label={lbl("estimated_etd", "Estimated ETD")} required={req("estimated_etd")} error={errors.estimated_etd?.message}>
              <input {...register("estimated_etd")} type="date" className={inputCls} />
            </Field>
          )}

          {/* Remarks */}
          {show("remarks") && (
            <Field label={lbl("remarks", "Remarks")} required={req("remarks")} error={errors.remarks?.message}>
              <textarea {...register("remarks")} rows={3} placeholder="Any additional notes for the accounts team…" className={inputCls} />
            </Field>
          )}

          {/* Server error */}
          {serverError && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              {serverError}
            </div>
          )}

          {/* Flagged supplier warning + Proceed / Withdraw */}
          {isFlaggedSupplier ? (
            <div className="space-y-3">
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>
                  <strong>{selectedSupplier?.name}</strong> is on the defaulted supplier list.
                  You may still submit — the request will require Head of Merchandiser approval before processing.
                </span>
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setShowFlagConfirm(true)}
                  className="flex-1 flex items-center justify-center gap-2 bg-gray-900 text-white rounded-xl px-4 py-3 text-sm font-semibold hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                >
                  {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Submitting…</> : "Proceed"}
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setValue("supplier_id", "")}
                  className="flex-1 flex items-center justify-center rounded-xl px-4 py-3 text-sm font-semibold border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-60 transition-colors"
                >
                  Withdraw
                </button>
              </div>
            </div>
          ) : (
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center gap-2 bg-gray-900 text-white rounded-xl px-4 py-3 text-sm font-semibold hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Submitting…</> : "Submit Request"}
            </button>
          )}

          <p className="text-center text-xs text-gray-400">
            Your request will be reviewed by the Sunshine finance team.
          </p>
        </form>
      </div>
    </div>

    {/* Flagged supplier confirmation modal */}
    {showFlagConfirm && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-lg p-6 w-full max-w-md space-y-4">
          <h3 className="font-semibold text-gray-900 text-base">Confirm Submission</h3>
          <p className="text-sm text-gray-600 leading-relaxed">
            <strong>{selectedSupplier?.name}</strong> is on the defaulted supplier list.
            If you proceed, this request will be sent to the{" "}
            <strong>Head of Merchandiser</strong> for approval before reaching the accounts team.
            You will be notified once it is reviewed.
          </p>
          <div className="flex gap-3 justify-end pt-1">
            <button
              type="button"
              onClick={() => setShowFlagConfirm(false)}
              className="px-4 py-2 text-sm border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                overrideFlagRef.current = true;
                setShowFlagConfirm(false);
                handleSubmit(onSubmit)();
              }}
              className="px-4 py-2 text-sm bg-gray-900 text-white rounded-xl hover:bg-gray-800 transition-colors"
            >
              Confirm &amp; Submit
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}

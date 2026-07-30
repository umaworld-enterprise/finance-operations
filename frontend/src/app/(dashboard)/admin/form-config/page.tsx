"use client";

import { useEffect, useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Save, Loader2, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { api } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FieldConfig {
  visible: boolean;
  required: boolean;
  label: string;
}

type FormFields = Record<string, FieldConfig>;

// ── Field definitions (display order + meta) ──────────────────────────────────

// "core" = always visible, only label is editable (DB requires a value)
const FIELD_META: { key: string; defaultLabel: string; group: string; core?: boolean }[] = [
  { key: "supplier_id",                    defaultLabel: "Select Supplier",                          group: "Parties",    core: true },
  { key: "customer_id",                    defaultLabel: "Select Customer",                          group: "Parties",    core: true },
  { key: "vertical_id",                    defaultLabel: "Vertical / Category",                      group: "Parties" },
  { key: "sunshine_invoice_number",        defaultLabel: "Sunshine Invoice No.",                     group: "Invoice" },
  { key: "supplier_invoice_number",        defaultLabel: "Supplier Invoice No.",                     group: "Invoice" },
  { key: "currency",                       defaultLabel: "Currency of Advance Payment",              group: "Financials" },
  { key: "total_supplier_invoice_amount",  defaultLabel: "Total Supplier Proforma Invoice Amount",   group: "Financials", core: true },
  // deposit_percentage / deposit_amount were retired — the public form now
  // collects Advance Payment Tranches (always shown, % system-calculated).
  // The estimated-shipment-date field was removed entirely (14 Jul 2026 change note, C5).
  { key: "remarks",                        defaultLabel: "Remarks",                                  group: "Extras" },
];

const DEFAULT_CONFIG: FormFields = Object.fromEntries(
  FIELD_META.map(({ key, defaultLabel }) => [
    key,
    { visible: true, required: ["supplier_id","customer_id","vertical_id","currency","total_supplier_invoice_amount"].includes(key), label: defaultLabel },
  ])
);

const GROUPS = ["Parties", "Invoice", "Financials", "Logistics", "Extras"];

// ── Toggle component ──────────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40 ${checked ? "bg-foreground" : "bg-muted-foreground/30"}`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-4" : "translate-x-0"}`}
      />
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FormConfigPage() {
  const [fields, setFields] = useState<FormFields>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<FormFields>("/admin/form-config")
      .then((res) => {
        if (res.data && Object.keys(res.data).length > 0) {
          setFields({ ...DEFAULT_CONFIG, ...res.data });
        }
      })
      .catch(() => toast.error("Failed to load form config."))
      .finally(() => setLoading(false));
  }, []);

  function update(key: string, patch: Partial<FieldConfig>) {
    setFields((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  }

  async function save() {
    setSaving(true);
    try {
      await api.put("/admin/form-config", fields);
      toast.success("Form configuration saved.");
    } catch {
      toast.error("Failed to save configuration.");
    } finally {
      setSaving(false);
    }
  }

  const grouped = GROUPS.map((g) => ({
    group: g,
    items: FIELD_META.filter((m) => m.group === g),
  }));

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="Public Form Configuration" subtitle="Control which fields appear on the public Supplier Advance Payment Request form" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-5">

        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to admin
        </Link>

        {/* Fixed field note */}
        <div className="rounded-xl border border-border bg-muted/40 px-5 py-3.5 flex items-start gap-3">
          <div className="mt-0.5 h-2 w-2 rounded-full bg-foreground shrink-0" />
          <div>
            <p className="text-sm font-medium text-foreground">Submitter Email is always required</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Per product policy, every public submission must include the submitter&apos;s email. This field cannot be removed.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            {grouped.map(({ group, items }) => (
              <Card key={group} className="overflow-hidden">
                <CardHeader className="pb-0">
                  <CardTitle className="text-sm">{group}</CardTitle>
                </CardHeader>

                <div className="divide-y divide-border">
                  {/* Header row */}
                  <div className="grid grid-cols-[1fr_auto_auto] gap-4 px-5 py-2.5 text-xs font-medium text-muted-foreground">
                    <span>Field label (shown on form)</span>
                    <span className="w-20 text-center">Visible</span>
                    <span className="w-20 text-center">Required</span>
                  </div>

                  {items.map(({ key, core }) => {
                    const cfg = fields[key] ?? DEFAULT_CONFIG[key];
                    return (
                      <div
                        key={key}
                        className={`grid grid-cols-[1fr_auto_auto] gap-4 items-center px-5 py-3.5 ${!cfg.visible && !core ? "opacity-50" : ""}`}
                      >
                        {/* Label input */}
                        <div className="flex items-center gap-2 min-w-0">
                          <input
                            type="text"
                            value={cfg.label}
                            onChange={(e) => update(key, { label: e.target.value })}
                            className="flex-1 min-w-0 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          />
                          {core && (
                            <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border border-border rounded px-1.5 py-0.5">
                              Core
                            </span>
                          )}
                        </div>

                        {/* Visible toggle */}
                        <div className="w-20 flex justify-center">
                          {core ? (
                            <span className="text-xs text-muted-foreground">Always</span>
                          ) : (
                            <Toggle
                              checked={cfg.visible}
                              onChange={(v) => update(key, { visible: v, required: v ? cfg.required : false })}
                            />
                          )}
                        </div>

                        {/* Required toggle */}
                        <div className="w-20 flex justify-center">
                          {core ? (
                            <span className="text-xs text-muted-foreground">Always</span>
                          ) : (
                            <Toggle
                              checked={cfg.required}
                              onChange={(v) => update(key, { required: v })}
                              disabled={!cfg.visible}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            ))}

            {/* Save */}
            <div className="flex justify-end">
              <Button onClick={save} disabled={saving} className="gap-2 min-w-28">
                {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : <><Save className="h-4 w-4" /> Save Changes</>}
              </Button>
            </div>

            {/* Preview link */}
            <p className="text-center text-xs text-muted-foreground">
              Preview the form at{" "}
              <a href="/form" target="_blank" className="underline underline-offset-2 hover:text-foreground">
                /form
              </a>
            </p>
          </>
        )}

      </main>
    </RoleGuard>
  );
}

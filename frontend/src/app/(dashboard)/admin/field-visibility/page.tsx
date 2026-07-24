"use client";

import { useState, useEffect } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Save, Loader2, Eye } from "lucide-react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";

type FieldConfig = Record<string, Record<string, boolean>>;

const GROUPS: { label: string; fields: { key: string; label: string; desc: string }[] }[] = [
  {
    label: "Financial",
    fields: [
      { key: "exchange_rate",                 label: "Exchange Rate",          desc: "FX rate applied to the invoice" },
      { key: "deposit_amount",                label: "Deposit Amount",         desc: "Actual deposit paid in currency" },
      { key: "deposit_percentage",            label: "Deposit %",              desc: "Deposit as % of total invoice" },
      { key: "total_supplier_invoice_amount", label: "Total Invoice Amount",   desc: "Full supplier invoice value" },
    ],
  },
  {
    label: "Payment Details",
    fields: [
      { key: "payment_date",             label: "Payment Date",           desc: "Date payment was made to supplier" },
      { key: "bank",                     label: "Bank",                   desc: "Bank used for the payment" },
      { key: "payment_reference_number", label: "Payment Reference #",    desc: "Bank transaction / cheque reference" },
      { key: "ship_date",                label: "Ship Date",              desc: "Date goods were dispatched" },
      { key: "accounts_remarks",         label: "Accounts Remarks",       desc: "Internal notes from the accounts team" },
    ],
  },
  {
    label: "Computed / Analytics",
    fields: [
      { key: "grace_etd",              label: "Grace ETD (10-day)",         desc: "ETD + grace period buffer" },
      { key: "etd_grace_overdue_days", label: "ETD Grace Overdue Days",     desc: "Days past grace ETD" },
      { key: "actual_etd_overdue_days",label: "Actual ETD Overdue Days",    desc: "Actual arrival vs promised ETD" },
      { key: "payment_to_ship_days",   label: "Payment → Ship Days",        desc: "Days from payment to shipment" },
      { key: "payment_to_request_days",label: "Payment → Request Days",     desc: "Days from request to payment" },
      { key: "cost_of_fund",           label: "Cost of Fund",               desc: "Notional financing cost accrued" },
      { key: "default_status",         label: "Default Status (Risk)",      desc: "On-time / Delayed / Critical classification" },
    ],
  },
  {
    label: "Audit / Creator",
    fields: [
      { key: "creator_info",      label: "Staff Name & Email",        desc: "Who submitted the request" },
      { key: "status_history",    label: "Status History Timeline",   desc: "Full status change log" },
      { key: "accounts_timestamp",label: "Accounts Timestamp & By",   desc: "When accounts last updated payment details" },
    ],
  },
];

const ROLES: { value: string; label: string }[] = [
  { value: "merchandiser",  label: "Merchandiser" },
  { value: "accounts_team", label: "Accounts Team" },
  { value: "finance_admin", label: "Finance Admin" },
];

async function fetchConfig(): Promise<FieldConfig> {
  const res = await api.get("/admin/field-visibility");
  return res.data;
}

async function saveConfig(config: FieldConfig): Promise<FieldConfig> {
  const res = await api.put("/admin/field-visibility", config);
  return res.data;
}

export default function FieldVisibilityPage() {
  const qc = useQueryClient();
  const { data: serverConfig, isLoading } = useQuery({
    queryKey: ["field-visibility-admin"],
    queryFn: fetchConfig,
  });

  const [config, setConfig] = useState<FieldConfig>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (serverConfig) {
      setConfig(serverConfig);
      setDirty(false);
    }
  }, [serverConfig]);

  const mutation = useMutation({
    mutationFn: saveConfig,
    onSuccess: (data) => {
      qc.setQueryData(["field-visibility-admin"], data);
      qc.invalidateQueries({ queryKey: ["field-visibility"] });
      toast.success("Field visibility saved.");
      setDirty(false);
    },
    onError: () => toast.error("Failed to save."),
  });

  function toggle(fieldKey: string, role: string) {
    setConfig((prev) => ({
      ...prev,
      [fieldKey]: {
        ...(prev[fieldKey] ?? {}),
        [role]: !(prev[fieldKey]?.[role] ?? false),
      },
    }));
    setDirty(true);
  }

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="Field Visibility" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        <div className="flex items-center justify-between">
          <Link
            href="/admin"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Back to admin
          </Link>
          <Button
            size="sm"
            onClick={() => mutation.mutate(config)}
            disabled={!dirty || mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-1.5" />
            )}
            Save changes
          </Button>
        </div>

        {isLoading ? (
          <div className="space-y-6">
            {GROUPS.map((group) => (
              <Card key={group.label}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    <CardTitle className="text-sm">{group.label}</CardTitle>
                  </div>
                  <CardDescription className="text-xs">
                    Super Admin always sees everything. Toggle visibility per role.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    {group.fields.map((f) => (
                      <div
                        key={f.key}
                        className="px-6 py-3 md:grid md:grid-cols-[1fr_repeat(3,120px)] md:gap-4 md:items-center space-y-2 md:space-y-0"
                      >
                        <div className="space-y-1.5">
                          <Skeleton className="h-4 w-36" />
                          <Skeleton className="h-3 w-52" />
                        </div>
                        <div className="flex flex-wrap gap-2 md:contents">
                          {ROLES.map((role) => (
                            <Skeleton key={role.value} className="h-7 w-20 rounded-full md:mx-auto" />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="space-y-6">
            {GROUPS.map((group) => (
              <Card key={group.label}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    <CardTitle className="text-sm">{group.label}</CardTitle>
                  </div>
                  <CardDescription className="text-xs">
                    Super Admin always sees everything. Toggle visibility per role.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border">
                    <div className="hidden md:grid grid-cols-[1fr_repeat(3,120px)] gap-4 px-6 py-2 text-xs font-medium text-muted-foreground bg-muted/40">
                      <span>Field</span>
                      {ROLES.map((r) => (
                        <span key={r.value} className="text-center">{r.label}</span>
                      ))}
                    </div>
                    {group.fields.map((f) => (
                      <div
                        key={f.key}
                        className="px-6 py-3 md:grid md:grid-cols-[1fr_repeat(3,120px)] md:gap-4 md:items-center space-y-2 md:space-y-0"
                      >
                        <div>
                          <p className="text-sm font-medium text-foreground">{f.label}</p>
                          <p className="text-xs text-muted-foreground">{f.desc}</p>
                        </div>
                        <div className="flex flex-wrap gap-2 md:contents">
                          {ROLES.map((role) => {
                            const active = config[f.key]?.[role.value] ?? false;
                            return (
                              <button
                                key={role.value}
                                onClick={() => toggle(f.key, role.value)}
                                className={`md:flex md:justify-center text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
                                  active
                                    ? "bg-primary text-primary-foreground border-transparent"
                                    : "bg-background text-muted-foreground border-border hover:border-primary/40"
                                }`}
                              >
                                <span className="md:hidden mr-1">{active ? "✓" : "○"}</span>
                                <span className="md:hidden">{role.label}</span>
                                <span className="hidden md:inline">{active ? "✓ Visible" : "Hidden"}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <div className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-4 py-3">
          <strong>Note:</strong> These settings control display only — they do not restrict data access at the API level. Super Admin always sees all fields regardless of this config.
        </div>
      </main>
    </RoleGuard>
  );
}

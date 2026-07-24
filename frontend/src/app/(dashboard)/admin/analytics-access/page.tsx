"use client";

import { useState, useEffect } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ArrowLeft, Save, Loader2, BarChart3 } from "lucide-react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";

const SECTIONS: { key: string; label: string; description: string }[] = [
  { key: "overdue_kpis",    label: "Overdue KPIs",      description: "Overdue deposit totals split by currency (USD / CNY / EUR) with notional gain/loss cards" },
  { key: "shipment_kpis",   label: "Shipment Report",   description: "5-card shipment pipeline: total overdue, ETD-grace, shipped, yet-to-ship, active entries" },
  { key: "delay_buckets",   label: "Delay Buckets",     description: "Aging analysis table: 11 delay ranges from Graced ETD to 135-150 days overdue" },
  { key: "by_merchandiser", label: "By Merchandiser",   description: "Overdue amounts, contribution %, avg delay, and notional gain grouped by staff member" },
  { key: "by_vertical",     label: "By Vertical",       description: "Same breakdown grouped by product category / vertical" },
  { key: "by_customer",     label: "By Customer",       description: "Customer-wise breakdown with max delay days and ETD pending count" },
];

const ROLES: { value: string; label: string }[] = [
  { value: "finance_admin",  label: "Finance Admin" },
  { value: "accounts_team",  label: "Accounts Team" },
  { value: "merchandiser",   label: "Merchandiser" },
];

type Permissions = Record<string, string[]>;

async function fetchPerms(): Promise<Permissions> {
  const res = await api.get("/admin/analytics-permissions");
  return res.data;
}

async function savePerms(perms: Permissions): Promise<Permissions> {
  const res = await api.put("/admin/analytics-permissions", perms);
  return res.data;
}

export default function AnalyticsAccessPage() {
  const qc = useQueryClient();
  const { data: serverPerms, isLoading } = useQuery({
    queryKey: ["analytics-permissions-admin"],
    queryFn: fetchPerms,
  });

  const [perms, setPerms] = useState<Permissions>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (serverPerms) {
      setPerms(serverPerms);
      setDirty(false);
    }
  }, [serverPerms]);

  const mutation = useMutation({
    mutationFn: savePerms,
    onSuccess: (data) => {
      qc.setQueryData(["analytics-permissions-admin"], data);
      qc.invalidateQueries({ queryKey: ["analytics-permissions"] });
      toast.success("Analytics permissions saved.");
      setDirty(false);
    },
    onError: () => toast.error("Failed to save permissions."),
  });

  function toggle(section: string, role: string) {
    setPerms((prev) => {
      const current = prev[section] ?? [];
      const next = current.includes(role)
        ? current.filter((r) => r !== role)
        : [...current, role];
      return { ...prev, [section]: next };
    });
    setDirty(true);
  }

  function hasRole(section: string, role: string) {
    return (perms[section] ?? []).includes(role);
  }

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="Analytics Access Control" />
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
            onClick={() => mutation.mutate(perms)}
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

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Analytics Section Permissions</CardTitle>
            </div>
            <CardDescription>
              Super Admin always has access to everything. Toggle which roles can see each
              analytics section. Changes take effect immediately after saving.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-16 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
              </div>
            ) : (
              <div className="divide-y divide-border">
                {/* Header row */}
                <div className="hidden md:grid grid-cols-[1fr_repeat(3,140px)] gap-4 px-6 py-2 text-xs font-medium text-muted-foreground bg-muted/40">
                  <span>Section</span>
                  {ROLES.map((r) => (
                    <span key={r.value} className="text-center">{r.label}</span>
                  ))}
                </div>

                {SECTIONS.map((section) => (
                  <div
                    key={section.key}
                    className="px-6 py-4 md:grid md:grid-cols-[1fr_repeat(3,140px)] md:gap-4 md:items-center space-y-3 md:space-y-0"
                  >
                    <div>
                      <p className="text-sm font-medium text-foreground">{section.label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{section.description}</p>
                    </div>

                    {/* Mobile: chips */}
                    <div className="flex flex-wrap gap-2 md:contents">
                      {ROLES.map((role) => {
                        const active = hasRole(section.key, role.value);
                        return (
                          <button
                            key={role.value}
                            onClick={() => toggle(section.key, role.value)}
                            className={`md:flex md:justify-center text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
                              active
                                ? "bg-primary text-primary-foreground border-transparent"
                                : "bg-background text-muted-foreground border-border hover:border-primary/40"
                            }`}
                          >
                            <span className="md:hidden mr-1">{active ? "✓" : "○"}</span>
                            <span className="md:hidden">{role.label}</span>
                            <span className="hidden md:inline">{active ? "✓ Enabled" : "Disabled"}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-4 py-3">
          <strong>Note:</strong> Granting access to a role (e.g. Finance Admin) covers all users
          with that role — no per-user configuration needed. Super Admin is always unrestricted.
        </div>
      </main>
    </RoleGuard>
  );
}

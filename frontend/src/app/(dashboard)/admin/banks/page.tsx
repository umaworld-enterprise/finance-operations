"use client";

// Bank master admin page (Aug 2026). Stores bank NAMES only — the tranche
// payment-details dropdown composes "{name} ({currency})" from the request's
// currency at render time.

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Landmark, Plus } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import masterService from "@/services/masterService";

const BANKS_KEY = ["banks", "all"] as const;

export default function BanksAdminPage() {
  const qc = useQueryClient();
  const { data: banks = [], isLoading } = useQuery({
    queryKey: [...BANKS_KEY],
    queryFn: masterService.getAllBanks,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [...BANKS_KEY] });
    qc.invalidateQueries({ queryKey: ["banks"] });
  };

  const createBank = useMutation({
    mutationFn: (name: string) => masterService.createBank(name),
    onSuccess: invalidate,
  });
  const updateBank = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name?: string; is_active?: boolean } }) =>
      masterService.updateBank(id, payload),
    onSuccess: invalidate,
  });

  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const doCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await createBank.mutateAsync(name);
      toast.success(`Bank "${name}" added.`);
      setNewName("");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to add the bank.");
    }
  };

  const doRename = async (id: string) => {
    const name = editName.trim();
    if (!name) return;
    try {
      await updateBank.mutateAsync({ id, payload: { name } });
      toast.success("Bank renamed.");
      setEditingId(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to rename the bank.");
    }
  };

  const doToggle = async (id: string, active: boolean) => {
    try {
      await updateBank.mutateAsync({ id, payload: { is_active: active } });
      toast.success(active ? "Bank activated." : "Bank deactivated.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update the bank.");
    }
  };

  const inputCls =
    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin"]}>
      <TopNav title="Banks" subtitle="Bank names for the tranche payment dropdown — the request's currency is appended automatically" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-3xl mx-auto w-full">
        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to admin
        </Link>

        <Card>
          <CardContent className="p-5 md:p-6 space-y-3">
            <h2 className="font-semibold text-foreground text-sm flex items-center gap-2">
              <Plus className="h-4 w-4" /> Add Bank
            </h2>
            <p className="text-xs text-muted-foreground">
              Enter the bank name only (e.g. &quot;DBS&quot;) — Accounts see it as
              &quot;€ DBS (EUR)&quot; based on each request&apos;s currency.
            </p>
            <div className="flex gap-3">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Bank name"
                className={inputCls}
              />
              <Button onClick={doCreate} disabled={!newName.trim() || createBank.isPending}>
                {createBank.isPending ? "Adding…" : "Add"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {isLoading ? (
              <Table><TableBody><TableSkeleton rows={3} cols={3} /></TableBody></Table>
            ) : banks.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={Landmark}
                  title="No banks yet"
                  description="Accounts cannot record tranche payment details until at least one bank exists."
                />
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Bank</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {banks.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell>
                        {editingId === b.id ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className={inputCls}
                          />
                        ) : (
                          <span className="font-medium text-sm">{b.name}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {b.is_active ? (
                          <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">Active</span>
                        ) : (
                          <span className="inline-flex items-center text-xs font-medium text-muted-foreground bg-muted border border-border px-2 py-0.5 rounded-full">Inactive</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          {editingId === b.id ? (
                            <>
                              <Button size="sm" onClick={() => doRename(b.id)} disabled={updateBank.isPending}>
                                Save
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                                Cancel
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => { setEditingId(b.id); setEditName(b.name); }}
                              >
                                Rename
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => doToggle(b.id, !b.is_active)}
                                disabled={updateBank.isPending}
                              >
                                {b.is_active ? "Deactivate" : "Activate"}
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>
    </RoleGuard>
  );
}

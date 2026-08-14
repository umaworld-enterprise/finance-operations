"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ArrowLeft, Check, Loader2, Pencil, Plus, X } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import {
  useAllPaymentTerms,
  useCreatePaymentTerm,
  useUpdatePaymentTerm,
  useDeletePaymentTerm,
} from "@/hooks/useMasters";
import { Pagination } from "@/components/ui/Pagination";
import { TableControls } from "@/components/ui/TableControls";
import { byString, useClientTable } from "@/hooks/useClientTable";
import type { PaymentTerm } from "@/types";

export default function PaymentTermsAdminPage() {
  const { data: terms = [], isLoading } = useAllPaymentTerms();
  const createTerm = useCreatePaymentTerm();
  const updateTerm = useUpdatePaymentTerm();
  const deleteTerm = useDeletePaymentTerm();

  const [newLabel, setNewLabel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");

  // Search / sort / pagination (10 Aug 2026, app-wide table controls).
  const termSorts = [
    { value: "label", label: "Label (A–Z)", compare: byString<PaymentTerm>((t) => t.label) },
    { value: "status", label: "Active first", compare: (a: PaymentTerm, b: PaymentTerm) => Number(b.is_active) - Number(a.is_active) },
  ];
  const termTable = useClientTable(terms, {
    searchHaystack: (t) => [t.label, t.is_active ? "active" : "inactive"],
    sortOptions: termSorts,
    pageSize: 20,
  });

  async function handleCreate() {
    const label = newLabel.trim();
    if (!label) return;
    try {
      await createTerm.mutateAsync({ label });
      setNewLabel("");
      toast.success(`"${label}" added.`);
    } catch {
      toast.error("Failed to add payment term.");
    }
  }

  function startEdit(id: string, label: string) {
    setEditingId(id);
    setEditLabel(label);
  }

  async function saveEdit(id: string) {
    const label = editLabel.trim();
    if (!label) return;
    try {
      await updateTerm.mutateAsync({ id, payload: { label } });
      setEditingId(null);
      toast.success("Payment term updated.");
    } catch {
      toast.error("Failed to update payment term.");
    }
  }

  async function handleToggle(id: string, currentActive: boolean) {
    try {
      await updateTerm.mutateAsync({ id, payload: { is_active: !currentActive } });
      toast.success(currentActive ? "Term deactivated." : "Term activated.");
    } catch {
      toast.error("Failed to update status.");
    }
  }

  async function handleDelete(id: string, label: string) {
    try {
      await deleteTerm.mutateAsync(id);
      toast.success(`"${label}" removed.`);
    } catch {
      toast.error("Failed to remove payment term.");
    }
  }

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin"]}>
      <TopNav title="Payment Terms" />
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          <Link
            href="/admin"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back to Admin
          </Link>

          <Card>
            <CardHeader>
              <CardTitle>Payment Terms</CardTitle>
              <CardDescription>
                Manage the list of payment terms available in the new request forms. Active terms appear in the search dropdown. Inactive terms are hidden but existing records are unaffected.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Add new */}
              <div className="flex gap-2">
                <Input
                  placeholder="New payment term label…"
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  className="flex-1"
                />
                <Button
                  onClick={handleCreate}
                  disabled={!newLabel.trim() || createTerm.isPending}
                  size="sm"
                  className="gap-1.5"
                >
                  {createTerm.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  Add
                </Button>
              </div>

              {isLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="rounded-md border p-3">
                  <TableControls
                    search={termTable.search}
                    onSearch={termTable.setSearch}
                    sort={termTable.sort}
                    onSort={termTable.setSort}
                    sortOptions={termSorts}
                    placeholder="Search payment terms…"
                  />
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8">#</TableHead>
                        <TableHead>Label</TableHead>
                        <TableHead className="w-24 text-center">Active</TableHead>
                        <TableHead className="w-24 text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {termTable.visible.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center py-8 text-muted-foreground text-sm">
                            {terms.length === 0 ? "No payment terms yet. Add one above." : "No terms match the search."}
                          </TableCell>
                        </TableRow>
                      )}
                      {termTable.visible.map((term, i) => (
                        <TableRow key={term.id} className={!term.is_active ? "opacity-50" : ""}>
                          <TableCell className="text-muted-foreground text-xs">
                            {(termTable.page - 1) * termTable.pageSize + i + 1}
                          </TableCell>
                          <TableCell>
                            {editingId === term.id ? (
                              <div className="flex gap-2 items-center">
                                <Input
                                  value={editLabel}
                                  onChange={(e) => setEditLabel(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") saveEdit(term.id);
                                    if (e.key === "Escape") setEditingId(null);
                                  }}
                                  className="h-7 text-sm"
                                  autoFocus
                                />
                                <button
                                  onClick={() => saveEdit(term.id)}
                                  className="text-green-600 hover:text-green-700"
                                  aria-label="Save"
                                >
                                  <Check className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={() => setEditingId(null)}
                                  className="text-muted-foreground hover:text-foreground"
                                  aria-label="Cancel"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              </div>
                            ) : (
                              <span className="text-sm">{term.label}</span>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            <Switch
                              checked={term.is_active}
                              onCheckedChange={() => handleToggle(term.id, term.is_active)}
                              aria-label={term.is_active ? "Deactivate" : "Activate"}
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-1">
                              {editingId !== term.id && (
                                <button
                                  onClick={() => startEdit(term.id, term.label)}
                                  className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                  aria-label="Edit"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                              )}
                              <button
                                onClick={() => handleDelete(term.id, term.label)}
                                className="p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                                aria-label="Delete"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination
                    page={termTable.page}
                    totalPages={termTable.totalPages}
                    total={termTable.total}
                    pageSize={termTable.pageSize}
                    onChange={termTable.setPage}
                  />
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                {terms.filter((t) => t.is_active).length} active · {terms.filter((t) => !t.is_active).length} inactive
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    </RoleGuard>
  );
}

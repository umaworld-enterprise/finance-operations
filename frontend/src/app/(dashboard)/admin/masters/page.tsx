"use client";

// Masters admin page (19 Aug 2026): Suppliers, Customers and Verticals —
// list (active + inactive), add, rename and activate/deactivate. The backend
// create/update endpoints existed since the initial schema; this page is the
// UI that was never built (suppliers previously entered only via imports).

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Boxes, Plus } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Label } from "@/components/ui/label";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Pagination } from "@/components/ui/Pagination";
import { TableControls } from "@/components/ui/TableControls";
import { byString, useClientTable } from "@/hooks/useClientTable";
import masterService from "@/services/masterService";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

function StatusPill({ active }: { active: boolean }) {
  return active ? (
    <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">Active</span>
  ) : (
    <span className="inline-flex items-center text-xs font-medium text-muted-foreground bg-muted border border-border px-2 py-0.5 rounded-full">Inactive</span>
  );
}

// One generic row shape covers all three masters — suppliers additionally
// carry a code and country.
interface MasterRow {
  id: string;
  name: string;
  is_active: boolean;
  supplier_code?: string;
  country?: string | null;
}

function MasterSection({
  kind,
  rows,
  isLoading,
  hasCode,
  onCreate,
  onUpdate,
  createHint,
}: {
  kind: string;
  rows: MasterRow[];
  isLoading: boolean;
  /** Suppliers carry a code (create-only) and a country. */
  hasCode?: boolean;
  onCreate: (values: { code: string; name: string; country: string }) => Promise<void>;
  onUpdate: (id: string, payload: { name?: string; country?: string; is_active?: boolean }) => Promise<void>;
  createHint: string;
}) {
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newCountry, setNewCountry] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editCountry, setEditCountry] = useState("");
  const [busy, setBusy] = useState(false);

  const sorts = [
    { value: "name", label: "Name (A–Z)", compare: byString<MasterRow>((r) => r.name) },
    { value: "status", label: "Active first", compare: (a: MasterRow, b: MasterRow) => Number(b.is_active) - Number(a.is_active) },
    ...(hasCode
      ? [{ value: "code", label: "Code (A–Z)", compare: byString<MasterRow>((r) => r.supplier_code ?? "") }]
      : []),
  ];
  const table = useClientTable(rows, {
    searchHaystack: (r) => [r.name, r.supplier_code, r.country, r.is_active ? "active" : "inactive"],
    sortOptions: sorts,
    pageSize: 20,
  });

  const canCreate = newName.trim() && (!hasCode || newCode.trim());

  const doCreate = async () => {
    if (!canCreate || busy) return;
    setBusy(true);
    try {
      await onCreate({ code: newCode.trim(), name: newName.trim(), country: newCountry.trim() });
      toast.success(`${kind} "${newName.trim()}" added.`);
      setNewCode(""); setNewName(""); setNewCountry("");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : `Failed to add the ${kind.toLowerCase()}.`);
    } finally {
      setBusy(false);
    }
  };

  const doSaveEdit = async (row: MasterRow) => {
    const name = editName.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      await onUpdate(row.id, {
        name,
        ...(hasCode ? { country: editCountry.trim() || undefined } : {}),
      });
      toast.success(`${kind} updated.`);
      setEditingId(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : `Failed to update the ${kind.toLowerCase()}.`);
    } finally {
      setBusy(false);
    }
  };

  const doToggle = async (row: MasterRow) => {
    if (busy) return;
    setBusy(true);
    try {
      await onUpdate(row.id, { is_active: !row.is_active });
      toast.success(row.is_active ? `${kind} deactivated — it disappears from the form dropdowns.` : `${kind} activated.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : `Failed to update the ${kind.toLowerCase()}.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-5 md:p-6 space-y-3">
          <h2 className="font-semibold text-foreground text-sm flex items-center gap-2">
            <Plus className="h-4 w-4" /> Add {kind}
          </h2>
          <p className="text-xs text-muted-foreground">{createHint}</p>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
            {hasCode && (
              <div>
                <Label htmlFor={`${kind}-code`}>Code</Label>
                <input
                  id={`${kind}-code`}
                  type="text"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  placeholder="e.g. SUP-0042"
                  className={`mt-1 ${inputCls}`}
                />
              </div>
            )}
            <div className={hasCode ? "" : "sm:col-span-2"}>
              <Label htmlFor={`${kind}-name`}>Name</Label>
              <input
                id={`${kind}-name`}
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={`${kind} name`}
                className={`mt-1 ${inputCls}`}
              />
            </div>
            {hasCode && (
              <div>
                <Label htmlFor={`${kind}-country`}>Country (optional)</Label>
                <input
                  id={`${kind}-country`}
                  type="text"
                  value={newCountry}
                  onChange={(e) => setNewCountry(e.target.value)}
                  placeholder="e.g. China"
                  className={`mt-1 ${inputCls}`}
                />
              </div>
            )}
            <Button onClick={doCreate} disabled={!canCreate || busy}>
              {busy ? "Saving…" : "Add"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardContent className="p-0">
          {isLoading ? (
            <Table><TableBody><TableSkeleton rows={4} cols={hasCode ? 5 : 3} /></TableBody></Table>
          ) : rows.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={Boxes}
                title={`No ${kind.toLowerCase()}s yet`}
                description={`${kind}s added here appear in the request form dropdowns immediately.`}
              />
            </div>
          ) : (
            <div className="p-4">
              <TableControls
                search={table.search}
                onSearch={table.setSearch}
                sort={table.sort}
                onSort={table.setSort}
                sortOptions={sorts}
                placeholder={`Search ${kind.toLowerCase()}s…`}
              />
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {hasCode && <TableHead>Code</TableHead>}
                      <TableHead>Name</TableHead>
                      {hasCode && <TableHead>Country</TableHead>}
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {table.visible.map((row) => (
                      <TableRow key={row.id}>
                        {hasCode && (
                          <TableCell className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                            {row.supplier_code}
                          </TableCell>
                        )}
                        <TableCell>
                          {editingId === row.id ? (
                            <input
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              className={inputCls}
                            />
                          ) : (
                            <span className="font-medium text-sm">{row.name}</span>
                          )}
                        </TableCell>
                        {hasCode && (
                          <TableCell>
                            {editingId === row.id ? (
                              <input
                                type="text"
                                value={editCountry}
                                onChange={(e) => setEditCountry(e.target.value)}
                                className={inputCls}
                              />
                            ) : (
                              <span className="text-sm text-muted-foreground">{row.country || "—"}</span>
                            )}
                          </TableCell>
                        )}
                        <TableCell><StatusPill active={row.is_active} /></TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            {editingId === row.id ? (
                              <>
                                <Button size="sm" onClick={() => doSaveEdit(row)} disabled={busy}>
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
                                  onClick={() => {
                                    setEditingId(row.id);
                                    setEditName(row.name);
                                    setEditCountry(row.country ?? "");
                                  }}
                                >
                                  Edit
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => doToggle(row)} disabled={busy}>
                                  {row.is_active ? "Deactivate" : "Activate"}
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <Pagination
                page={table.page}
                totalPages={table.totalPages}
                total={table.total}
                pageSize={table.pageSize}
                onChange={table.setPage}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function MastersAdminPage() {
  const qc = useQueryClient();
  const invalidate = () => {
    // Admin lists AND the request-form dropdown queries.
    for (const key of ["suppliers", "customers", "verticals"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
    qc.invalidateQueries({ queryKey: ["masters"] });
  };

  const { data: suppliers = [], isLoading: sLoading } = useQuery({
    queryKey: ["masters", "suppliers", "all"],
    queryFn: masterService.getAllSuppliers,
  });
  const { data: customers = [], isLoading: cLoading } = useQuery({
    queryKey: ["masters", "customers", "all"],
    queryFn: masterService.getAllCustomers,
  });
  const { data: verticals = [], isLoading: vLoading } = useQuery({
    queryKey: ["masters", "verticals", "all"],
    queryFn: masterService.getAllVerticals,
  });

  const createSupplier = useMutation({
    mutationFn: (v: { code: string; name: string; country: string }) =>
      masterService.createSupplier({
        supplier_code: v.code,
        name: v.name,
        ...(v.country ? { country: v.country } : {}),
      }),
    onSuccess: invalidate,
  });
  const updateSupplier = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name?: string; country?: string; is_active?: boolean } }) =>
      masterService.updateSupplier(id, payload),
    onSuccess: invalidate,
  });
  const createCustomer = useMutation({
    mutationFn: (v: { name: string }) => masterService.createCustomer(v.name),
    onSuccess: invalidate,
  });
  const updateCustomer = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name?: string; is_active?: boolean } }) =>
      masterService.updateCustomer(id, payload),
    onSuccess: invalidate,
  });
  const createVertical = useMutation({
    mutationFn: (v: { name: string }) => masterService.createVertical(v.name),
    onSuccess: invalidate,
  });
  const updateVertical = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name?: string; is_active?: boolean } }) =>
      masterService.updateVertical(id, payload),
    onSuccess: invalidate,
  });

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin"]}>
      <TopNav
        title="Masters"
        subtitle="Suppliers, customers and verticals — the request-form dropdowns draw from these lists"
      />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-4xl mx-auto w-full">
        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to admin
        </Link>

        <Tabs defaultValue="suppliers">
          <TabsList className="mb-1">
            <TabsTrigger value="suppliers">Suppliers ({suppliers.length})</TabsTrigger>
            <TabsTrigger value="customers">Customers ({customers.length})</TabsTrigger>
            <TabsTrigger value="verticals">Verticals ({verticals.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="suppliers">
            <MasterSection
              kind="Supplier"
              rows={suppliers}
              isLoading={sLoading}
              hasCode
              createHint="Code and name are required; the code must be unique and cannot be changed later. Deactivating hides the supplier from new requests — history is untouched."
              onCreate={async (v) => { await createSupplier.mutateAsync(v); }}
              onUpdate={async (id, payload) => { await updateSupplier.mutateAsync({ id, payload }); }}
            />
          </TabsContent>

          <TabsContent value="customers">
            <MasterSection
              kind="Customer"
              rows={customers}
              isLoading={cLoading}
              createHint="Customers appear in the request form's Select Customer dropdown."
              onCreate={async (v) => { await createCustomer.mutateAsync(v); }}
              onUpdate={async (id, payload) => { await updateCustomer.mutateAsync({ id, payload }); }}
            />
          </TabsContent>

          <TabsContent value="verticals">
            <MasterSection
              kind="Vertical"
              rows={verticals}
              isLoading={vLoading}
              createHint="Verticals / categories appear in the request form's Vertical dropdown."
              onCreate={async (v) => { await createVertical.mutateAsync(v); }}
              onUpdate={async (id, payload) => { await updateVertical.mutateAsync({ id, payload }); }}
            />
          </TabsContent>
        </Tabs>
      </main>
    </RoleGuard>
  );
}

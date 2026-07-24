"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { StatCard } from "@/components/ui/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/ui/field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { useDefaultedSuppliers, useFlagSupplier, useResolveDefault, useSuppliers } from "@/hooks/useMasters";
import { formatDate } from "@/lib/utils";
import { AlertTriangle, CheckCircle, ShieldOff, Plus, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"] as const;

const flagSchema = z.object({
  supplier_id: z.string().min(1, "Select a supplier"),
  outstanding_amount: z.coerce.number().positive("Must be a positive amount"),
  currency: z.enum(CURRENCIES),
  default_reason: z.string().min(5, "Please provide a reason (min 5 chars)"),
  flagged_date: z.string().min(1, "Select a date"),
});

type FlagForm = z.infer<typeof flagSchema>;

export default function FinanceDashboard() {
  const router = useRouter();
  const { data: defaulted = [], isLoading } = useDefaultedSuppliers();
  const { data: suppliers = [] } = useSuppliers();
  const flagSupplier = useFlagSupplier();
  const resolveDefault = useResolveDefault();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolveConfirm, setResolveConfirm] = useState<string | null>(null);

  const active = defaulted.filter((d) => d.is_active);
  const resolved = defaulted.filter((d) => !d.is_active);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FlagForm>({
    resolver: zodResolver(flagSchema),
    defaultValues: {
      currency: "USD",
      flagged_date: new Date().toISOString().split("T")[0],
    },
  });

  const onFlag = async (data: FlagForm) => {
    try {
      await flagSupplier.mutateAsync(data);
      toast.success("Supplier flagged as defaulted.");
      reset();
      setDialogOpen(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to flag supplier.");
    }
  };

  const handleResolve = async (id: string) => {
    setResolvingId(id);
    try {
      await resolveDefault.mutateAsync(id);
      toast.success("Supplier flag resolved.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to resolve.");
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <RoleGuard allowedRoles={["finance_admin", "super_admin"]}>
      <TopNav title="Supplier Risk" subtitle="Manage defaulted supplier flags" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6">

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard label="Active Flags" value={active.length} icon={AlertTriangle} />
          <StatCard label="Resolved" value={resolved.length} icon={CheckCircle} />
          <StatCard label="Total" value={defaulted.length} icon={ShieldOff} />
        </div>

        <Card className="overflow-hidden">
          <CardHeader className="pb-3 border-b border-border">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <CardTitle className="text-sm font-semibold text-foreground">Defaulted Suppliers</CardTitle>
              <div className="flex items-center gap-3">
                {active.length > 0 && (
                  <Badge variant="destructive">{active.length} active</Badge>
                )}
                <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                  <DialogTrigger asChild>
                    <Button size="sm" variant="destructive" className="w-full sm:w-auto">
                      <Plus className="h-4 w-4 mr-1" />
                      Flag Supplier
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Flag Defaulted Supplier</DialogTitle>
                      <DialogDescription>
                        Flagged suppliers will be blocked from new deposit requests.
                      </DialogDescription>
                    </DialogHeader>

                    <form onSubmit={handleSubmit(onFlag)} className="space-y-4">
                      <Field
                        label="Supplier"
                        required
                        tooltip="Select the supplier to flag. They will be blocked from receiving new advance deposits."
                        error={errors.supplier_id?.message}
                        variant="select"
                        {...register("supplier_id")}
                      >
                        <option value="">— select supplier —</option>
                        {suppliers.map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </Field>

                      <div className="grid grid-cols-2 gap-3">
                        <Field
                          label="Outstanding Amount"
                          required
                          tooltip="The unpaid amount owed by this supplier."
                          error={errors.outstanding_amount?.message}
                          type="number"
                          step="0.01"
                          min="0.01"
                          placeholder="0.00"
                          {...register("outstanding_amount")}
                        />
                        <Field
                          label="Currency"
                          required
                          variant="select"
                          {...register("currency")}
                        >
                          {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                        </Field>
                      </div>

                      <Field
                        label="Flagged Date"
                        required
                        error={errors.flagged_date?.message}
                        type="date"
                        {...register("flagged_date")}
                      />

                      <Field
                        label="Reason / Notes"
                        required
                        tooltip="Explain why this supplier is being flagged. Visible to your team."
                        error={errors.default_reason?.message}
                        variant="textarea"
                        rows={3}
                        placeholder="Describe why this supplier is being flagged…"
                        {...register("default_reason")}
                      />

                      <DialogFooter>
                        <DialogClose asChild>
                          <Button type="button" variant="outline">Cancel</Button>
                        </DialogClose>
                        <Button type="submit" variant="destructive" disabled={isSubmitting}>
                          {isSubmitting ? "Flagging…" : "Flag Supplier"}
                        </Button>
                      </DialogFooter>
                    </form>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {isLoading ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Supplier</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Flagged</TableHead>
                    <TableHead className="hidden md:table-cell">Resolved</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableSkeleton rows={5} cols={6} />
                </TableBody>
              </Table>
            ) : defaulted.length === 0 ? (
              <div className="text-center py-16 text-muted-foreground">
                <CheckCircle2 className="mx-auto h-10 w-10 mb-2 text-muted-foreground" />
                <p className="font-medium text-foreground">No defaulted suppliers</p>
                <p className="text-sm mt-1">All suppliers are in good standing.</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Supplier</TableHead>
                    <TableHead className="hidden md:table-cell">Reason</TableHead>
                    <TableHead>Flagged</TableHead>
                    <TableHead className="hidden md:table-cell">Resolved</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {defaulted.map((d) => (
                    <TableRow
                      key={d.id}
                      onClick={() => router.push(`/analytics/supplier/${d.supplier_id}`)}
                      className={`cursor-pointer ${d.is_active ? "" : "opacity-60"}`}
                    >
                      <TableCell className="font-medium text-foreground">
                        {d.supplier_name || d.supplier_id}
                      </TableCell>
                      <TableCell className="hidden md:table-cell text-muted-foreground max-w-xs">
                        <span className="line-clamp-2 text-sm">{d.default_reason}</span>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">{formatDate(d.flagged_date)}</TableCell>
                      <TableCell className="hidden md:table-cell text-muted-foreground text-sm">
                        {d.resolved_date ? formatDate(d.resolved_date) : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={d.is_active ? "destructive" : "secondary"}>
                          {d.is_active ? "Active" : "Resolved"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {d.is_active && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              setResolveConfirm(d.id);
                            }}
                            disabled={resolvingId === d.id}
                          >
                            {resolvingId === d.id ? "Resolving…" : "Resolve"}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <ConfirmDialog
          open={resolveConfirm !== null}
          onOpenChange={(open) => !open && setResolveConfirm(null)}
          title="Resolve this defaulted supplier flag?"
          description="The supplier will be unblocked and can receive new advance deposit requests again."
          confirmLabel="Yes, resolve flag"
          onConfirm={() => resolveConfirm && handleResolve(resolveConfirm)}
        />
      </main>
    </RoleGuard>
  );
}

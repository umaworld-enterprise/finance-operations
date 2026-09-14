"use client";

// Merchandiser form editing (2 Sep 2026): the request's OWNER can edit the
// form fields while the request is still pending (HoM approval or the
// payment queue) AND Accounts have not acted on it in any way — the same
// gate the backend enforces. Deposit amount stays tranche-derived and is
// deliberately absent here.

import { useState } from "react";
import { toast } from "sonner";
import { ChevronDown, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useCustomers, useSuppliers, useVerticals } from "@/hooks/useMasters";
import { useUpdateRequest } from "@/hooks/useRequests";
import type { DepositRequestDetail } from "@/types";

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD"];

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function EditRequestForm({ request }: { request: DepositRequestDetail }) {
  const { data: suppliers = [] } = useSuppliers();
  const { data: customers = [] } = useCustomers();
  const { data: verticals = [] } = useVerticals();
  const updateRequest = useUpdateRequest(request.id);

  const [open, setOpen] = useState(false);
  const [supplierId, setSupplierId] = useState(request.supplier.id);
  const [customerId, setCustomerId] = useState(request.customer.id);
  const [verticalId, setVerticalId] = useState(request.vertical?.id ?? "");
  const [supplierInv, setSupplierInv] = useState(request.supplier_invoice_number ?? "");
  const [sunshineInv, setSunshineInv] = useState(request.sunshine_invoice_number ?? "");
  const [currency, setCurrency] = useState(request.currency ?? "");
  const [etd, setEtd] = useState(request.estimated_etd ?? "");
  const [total, setTotal] = useState(String(request.total_supplier_invoice_amount ?? ""));

  const totalNum = Number(total);
  const canSave =
    !!supplierId && !!customerId && totalNum > 0 && !updateRequest.isPending;

  const doSave = async () => {
    if (!canSave) return;
    try {
      await updateRequest.mutateAsync({
        supplier_id: supplierId,
        customer_id: customerId,
        ...(verticalId ? { vertical_id: verticalId } : {}),
        supplier_invoice_number: supplierInv.trim() || undefined,
        sunshine_invoice_number: sunshineInv.trim() || undefined,
        ...(currency ? { currency } : {}),
        total_supplier_invoice_amount: totalNum,
        ...(etd ? { estimated_etd: etd } : {}),
      });
      toast.success("Request updated — every change is recorded in the audit log.");
      setOpen(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update the request.");
    }
  };

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-muted/40 transition-colors"
      >
        <span className="flex items-center gap-2 font-semibold text-foreground text-sm">
          <Pencil className="h-4 w-4" />
          Edit Request
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <CardContent className="border-t border-border p-5 md:p-6 space-y-4 bg-muted/20">
          <p className="text-xs text-muted-foreground">
            Editable until the Accounts team acts on this request. The deposit
            amount is managed through the tranches below. Every change is
            audited and the Accounts team works from the latest values.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="er-supplier">Supplier</Label>
              <select id="er-supplier" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className={`mt-1 ${inputCls}`}>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="er-customer">Customer</Label>
              <select id="er-customer" value={customerId} onChange={(e) => setCustomerId(e.target.value)} className={`mt-1 ${inputCls}`}>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="er-vertical">Vertical / Category</Label>
              <select id="er-vertical" value={verticalId} onChange={(e) => setVerticalId(e.target.value)} className={`mt-1 ${inputCls}`}>
                <option value="">—</option>
                {verticals.map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="er-currency">Currency</Label>
              <select id="er-currency" value={currency} onChange={(e) => setCurrency(e.target.value)} className={`mt-1 ${inputCls}`}>
                <option value="">—</option>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="er-supplier-inv">Supplier Proforma Invoice #</Label>
              <input id="er-supplier-inv" type="text" value={supplierInv} onChange={(e) => setSupplierInv(e.target.value)} className={`mt-1 ${inputCls}`} />
            </div>
            <div>
              <Label htmlFor="er-sunshine-inv">Sunshine Invoice #</Label>
              <input id="er-sunshine-inv" type="text" value={sunshineInv} onChange={(e) => setSunshineInv(e.target.value)} className={`mt-1 ${inputCls}`} />
            </div>
            <div>
              <Label htmlFor="er-etd">ETD</Label>
              <input id="er-etd" type="date" value={etd} onChange={(e) => setEtd(e.target.value)} className={`mt-1 ${inputCls}`} />
            </div>
            <div>
              <Label htmlFor="er-total">Total Supplier Proforma Invoice Amount</Label>
              <input
                id="er-total" type="number" step="0.01" min="0"
                value={total} onChange={(e) => setTotal(e.target.value)}
                className={`mt-1 ${inputCls}`}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={doSave} disabled={!canSave}>
              {updateRequest.isPending ? "Saving…" : "Save Changes"}
            </Button>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

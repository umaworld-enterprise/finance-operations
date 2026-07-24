"use client";

import { useEffect, useState } from "react";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { TopNav } from "@/components/layout/TopNav";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import masterService from "@/services/masterService";
import requestService from "@/services/requestService";
import Link from "next/link";

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"];

interface Row { id: string; name: string }

function TestFormInner() {
  const [suppliers, setSuppliers] = useState<Row[]>([]);
  const [customers, setCustomers] = useState<Row[]>([]);
  const [verticals, setVerticals] = useState<Row[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [result, setResult] = useState<string>("");

  const [form, setForm] = useState({
    supplier_id: "",
    customer_id: "",
    vertical_id: "",
    sunshine_invoice_number: "",
    supplier_invoice_number: "",
    currency: "USD",
    exchange_rate: "",
    deposit_amount: "",
    deposit_percentage: "",
    total_supplier_invoice_amount: "",
    estimated_shipment_date: "",
    estimated_etd: "",
    remarks: "",
  });

  useEffect(() => {
    const load = async () => {
      const [s, c, v] = await Promise.all([
        masterService.getSuppliers(),
        masterService.getCustomers(),
        masterService.getVerticals(),
      ]);
      setSuppliers(s.map((x) => ({ id: x.id, name: x.name })));
      setCustomers(c.map((x) => ({ id: x.id, name: x.name })));
      setVerticals(v.map((x) => ({ id: x.id, name: x.name })));
    };
    load();
  }, []);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus("loading");

    try {
      const data = await requestService.create({
        supplier_id: form.supplier_id,
        customer_id: form.customer_id,
        vertical_id: form.vertical_id,
        sunshine_invoice_number: form.sunshine_invoice_number || undefined,
        supplier_invoice_number: form.supplier_invoice_number || undefined,
        currency: form.currency,
        exchange_rate: form.exchange_rate ? parseFloat(form.exchange_rate) : undefined,
        deposit_amount: parseFloat(form.deposit_amount),
        deposit_percentage: parseFloat(form.deposit_percentage),
        total_supplier_invoice_amount: parseFloat(form.total_supplier_invoice_amount),
        estimated_shipment_date: form.estimated_shipment_date,
        estimated_etd: form.estimated_etd || undefined,
        remarks: form.remarks || undefined,
      });
      setResult(`Request created!\nRequest #: ${data.request_number}\nID: ${data.id}`);
      setStatus("success");
    } catch (err: unknown) {
      setResult(`Error: ${err instanceof Error ? err.message : "Failed to create request."}`);
      setStatus("error");
    }
  };

  return (
    <>
      <TopNav title="Test Form" subtitle="Submits via the backend API for manual testing" />
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <div className="max-w-2xl mx-auto">
          <Card className="p-6 space-y-5">
            <form onSubmit={submit} className="space-y-5">
              <Field label="Supplier" required>
                <select required value={form.supplier_id} onChange={e => set("supplier_id", e.target.value)}>
                  <option value="">— select supplier —</option>
                  {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>

              <Field label="Customer" required>
                <select required value={form.customer_id} onChange={e => set("customer_id", e.target.value)}>
                  <option value="">— select customer —</option>
                  {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>

              <Field label="Vertical / Category" required>
                <select required value={form.vertical_id} onChange={e => set("vertical_id", e.target.value)}>
                  <option value="">— select vertical —</option>
                  {verticals.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </Field>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Sunshine Invoice #">
                  <input type="text" value={form.sunshine_invoice_number} onChange={e => set("sunshine_invoice_number", e.target.value)} placeholder="INV-XXXXX" />
                </Field>
                <Field label="Supplier Invoice #">
                  <input type="text" value={form.supplier_invoice_number} onChange={e => set("supplier_invoice_number", e.target.value)} />
                </Field>
                <Field label="Currency" required>
                  <select required value={form.currency} onChange={e => set("currency", e.target.value)}>
                    {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Exchange Rate to USD">
                  <input type="number" step="0.000001" value={form.exchange_rate} onChange={e => set("exchange_rate", e.target.value)} placeholder="e.g. 84.5" />
                </Field>
                <Field label="Total Invoice Amount" required>
                  <input type="number" required step="0.01" min="0.01" value={form.total_supplier_invoice_amount} onChange={e => set("total_supplier_invoice_amount", e.target.value)} placeholder="0.00" />
                </Field>
                <Field label="Deposit %" required>
                  <input type="number" required step="0.01" min="0.01" max="100" value={form.deposit_percentage} onChange={e => set("deposit_percentage", e.target.value)} placeholder="e.g. 30" />
                </Field>
                <Field label="Deposit Amount" required>
                  <input type="number" required step="0.01" min="0.01" value={form.deposit_amount} onChange={e => set("deposit_amount", e.target.value)} placeholder="0.00" />
                </Field>
                <Field label="Est. Shipment Date" required>
                  <input type="date" required value={form.estimated_shipment_date} onChange={e => set("estimated_shipment_date", e.target.value)} />
                </Field>
                <Field label="Estimated ETD">
                  <input type="date" value={form.estimated_etd} onChange={e => set("estimated_etd", e.target.value)} />
                </Field>
              </div>

              <Field label="Remarks / Notes">
                <textarea rows={3} value={form.remarks} onChange={e => set("remarks", e.target.value)} placeholder="Any additional notes..." />
              </Field>

              {result && (
                <pre className={`text-sm rounded-lg p-4 whitespace-pre-wrap ${status === "success" ? "bg-muted text-foreground border border-border" : "bg-muted text-foreground border border-border"}`}>
                  {result}
                </pre>
              )}

              <Button type="submit" disabled={status === "loading"} className="w-full">
                {status === "loading" ? "Submitting…" : "Submit Advance Deposit Request"}
              </Button>

              <p className="text-xs text-center text-muted-foreground">
                After submitting, go to <Link href="/accounts" className="text-foreground underline">/accounts</Link> to process the payment, or <Link href="/admin" className="text-foreground underline">/admin</Link> to see the admin overview.
              </p>
            </form>
          </Card>
        </div>
      </main>
    </>
  );
}

export default function TestFormPage() {
  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TestFormInner />
    </RoleGuard>
  );
}

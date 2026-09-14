"use client";

// Bulk payment dialog (9 Sep 2026): Accounts selected several requests of
// the SAME supplier — one shared payment-details form + ONE TT copy pays
// each request's next payable tranche in a single atomic action.

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Landmark } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBanks } from "@/hooks/useMasters";
import { useBulkPay } from "@/hooks/useRequests";
import { formatCurrency, formatDate, todayLocalISO } from "@/lib/utils";
import type { DepositRequest, PaymentTranche } from "@/types";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

const SECONDARY_CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"];

export function nextPayableTranche(req: DepositRequest): PaymentTranche | null {
  const payable = (req.tranches ?? [])
    .filter((t) => t.status === "unpaid" && (t.released_at != null || t.tranche_number === 1))
    .sort((a, b) => a.tranche_number - b.tranche_number);
  return payable[0] ?? null;
}

export function BulkPayDialog({
  open,
  requests,
  onClose,
  onDone,
}: {
  open: boolean;
  /** The selected requests — all same supplier (enforced by the selection UI
   * and again server-side). */
  requests: DepositRequest[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { data: banks = [] } = useBanks();
  const bulkPay = useBulkPay();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [paymentDate, setPaymentDate] = useState(todayLocalISO());
  const [bank, setBank] = useState("");
  const [reference, setReference] = useState("");
  const [remarks, setRemarks] = useState("");
  const [secondaryCurrency, setSecondaryCurrency] = useState("");
  const [secondaryAmount, setSecondaryAmount] = useState("");
  const [fileName, setFileName] = useState("");

  if (!open || requests.length === 0) return null;

  const supplier = requests[0].supplier?.name ?? "—";
  const rows = requests.map((r) => ({ req: r, tranche: nextPayableTranche(r) }));
  const totalsByCurrency = new Map<string, number>();
  for (const { req, tranche } of rows) {
    if (!tranche) continue;
    const cur = req.currency ?? "—";
    totalsByCurrency.set(cur, (totalsByCurrency.get(cur) ?? 0) + Number(tranche.amount));
  }

  const doPay = async () => {
    const file = fileRef.current?.files?.[0];
    if (!paymentDate || !bank.trim()) {
      toast.error("Payment date and bank are required.");
      return;
    }
    if (!file) {
      toast.error("Attach the bank's TT copy — it is attached to every selected request.");
      return;
    }
    if (Number(secondaryAmount) > 0 && !secondaryCurrency) {
      toast.error("Select the secondary currency for the secondary amount.");
      return;
    }
    try {
      const result = await bulkPay.mutateAsync({
        requestIds: requests.map((r) => r.id),
        paymentDate,
        bank: bank.trim(),
        paymentReferenceNumber: reference.trim() || undefined,
        accountsRemarks: remarks.trim() || undefined,
        secondaryCurrency: secondaryCurrency || undefined,
        secondaryAmount: Number(secondaryAmount) > 0 ? Number(secondaryAmount) : undefined,
        file,
      });
      toast.success(
        `${result.paid.length} tranche${result.paid.length === 1 ? "" : "s"} paid for ${supplier} — merchandisers notified.`,
      );
      onDone();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Bulk payment failed — nothing was saved.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-card rounded-xl border border-border shadow-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Landmark className="h-4 w-4 text-muted-foreground" />
          <h3 className="font-semibold text-foreground">
            Bulk Payment — {supplier}
          </h3>
        </div>
        <p className="text-xs text-muted-foreground">
          The details below and ONE TT copy are saved onto each request&apos;s next payable
          tranche, and every tranche is marked PAID in one atomic action (any failure rolls
          the whole batch back). All selected requests belong to this supplier.
        </p>

        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-xs text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2">Request #</th>
                <th className="text-left px-3 py-2">Invoice #</th>
                <th className="text-left px-3 py-2">Tranche</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-left px-3 py-2">Tentative</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ req, tranche }) => (
                <tr key={req.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono text-xs font-semibold">{req.request_number}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{req.sunshine_invoice_number ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{tranche?.label ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {tranche ? formatCurrency(tranche.amount, req.currency ?? undefined) : "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                    {tranche?.tentative_payment_date ? formatDate(tranche.tentative_payment_date) : "—"}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-border bg-muted/40 font-semibold">
                <td className="px-3 py-2 text-sm" colSpan={3}>Total</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {[...totalsByCurrency.entries()]
                    .map(([cur, sum]) => formatCurrency(sum, cur === "—" ? undefined : cur))
                    .join(" + ")}
                </td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              Payment date<span className="text-foreground ml-0.5">*</span>
            </p>
            <input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} className={inputCls} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              Bank<span className="text-foreground ml-0.5">*</span>
            </p>
            <select value={bank} onChange={(e) => setBank(e.target.value)} className={inputCls} disabled={banks.length === 0}>
              <option value="">{banks.length === 0 ? "No banks configured" : "Select bank"}</option>
              {banks.map((b) => (
                <option key={b.id} value={b.name}>{b.name}</option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Payment ref. # (optional)</p>
            <input type="text" value={reference} onChange={(e) => setReference(e.target.value)} className={inputCls} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Secondary currency (optional)</p>
            <select value={secondaryCurrency} onChange={(e) => setSecondaryCurrency(e.target.value)} className={inputCls}>
              <option value="">None</option>
              {SECONDARY_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Secondary amount (optional)</p>
            <input type="number" step="0.01" min="0" value={secondaryAmount} onChange={(e) => setSecondaryAmount(e.target.value)} className={inputCls} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Accounts remarks (optional)</p>
            <input type="text" value={remarks} onChange={(e) => setRemarks(e.target.value)} className={inputCls} />
          </div>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-1">
            TT copy<span className="text-foreground ml-0.5">*</span> — one document, attached to every selected request
          </p>
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")}
              className="hidden"
            />
            <Button size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>
              {fileName ? "Change TT Copy" : "Attach TT Copy"}
            </Button>
            {fileName && <span className="text-xs text-muted-foreground">{fileName}</span>}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose} disabled={bulkPay.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={doPay} disabled={bulkPay.isPending}>
            {bulkPay.isPending
              ? "Paying…"
              : `Pay ${rows.length} Request${rows.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>
    </div>
  );
}

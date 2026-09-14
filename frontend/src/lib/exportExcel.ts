// Excel export for request tables (2 Sep 2026): bank-ledger columns plus
// context (Request #, Request Date, Status, Payment Date) — one format for
// every tab. SheetJS is imported lazily so it stays out of the main bundle.

import { formatDate } from "@/lib/utils";
import type { DepositRequest, PendingReleaseRow } from "@/types";

/** Latest paid tranche's payment date — the request row's "paid on". */
export function latestPaymentDate(req: DepositRequest): string | null {
  const dates = (req.tranches ?? [])
    .filter((t) => t.status === "paid" && t.payment_date)
    .map((t) => t.payment_date as string)
    .sort();
  return dates[dates.length - 1] ?? null;
}

function statusLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

async function writeSheet(data: Record<string, unknown>[], filename: string, sheet: string) {
  const XLSX = await import("xlsx");
  const ws = XLSX.utils.json_to_sheet(data);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheet);
  XLSX.writeFile(wb, filename);
}

export async function exportRequestsToExcel(
  rows: DepositRequest[], filename: string,
): Promise<void> {
  await writeSheet(
    rows.map((r) => ({
      "Request #": r.request_number,
      "Request Date": formatDate(r.created_at),
      "Supplier": r.supplier?.name ?? "",
      "Supplier Proforma Invoice No.": r.supplier_invoice_number ?? "",
      "Sunshine Invoice No.": r.sunshine_invoice_number ?? "",
      "Selected Customer": r.customer?.name ?? "",
      "Currency": r.currency ?? "",
      "Deposit Amount": Number(r.deposit_amount),
      "Status": statusLabel(r.current_status),
      "Payment Date": latestPaymentDate(r) ? formatDate(latestPaymentDate(r)) : "",
    })),
    filename,
    "Requests",
  );
}

// Bank-ledger format (4 Sep 2026, executive request; final column sequence
// same day): Date | Supplier | Supplier Proforma Invoice # | File Nos. |
// Customer | Curr | EURO/CNY | Rate | Debit | Credit | BALANCE. One row per
// tranche — "Curr" carries the currency CODE, "Debit" the tranche amount; a
// paid tranche is dated by its payment date, an unpaid one by the request
// date. EURO/CNY (kept empty by client decision for now), Rate, Credit and
// BALANCE are maintained manually in Excel. The same entries feed both the
// Excel export and the on-screen Bank Ledger tab.
export interface BankLedgerEntry {
  date: string | null;
  supplier: string;
  /** The "Supplier Proforma Invoice #" column (replaced Voucher No.). */
  supplier_invoice: string;
  file_nos: string;
  customer: string;
  /** The "Curr" column — the request's currency code. */
  curr: string;
  /** The "Debit" column — the tranche amount in that currency. */
  amount: number;
}

export function bankLedgerEntries(
  rows: DepositRequest[],
  opts?: {
    /** Pending Payments view (4 Sep 2026, the "1323" case): list only the
     * tranches still to be paid — paid tranches never belong in a PENDING
     * payments sheet. */
    unpaidOnly?: boolean;
  },
): BankLedgerEntry[] {
  const entries = rows.flatMap((r) =>
    (r.tranches ?? [])
      .filter((t) => t.status !== "rejected")
      .filter((t) => (opts?.unpaidOnly ? t.status === "unpaid" : true))
      .map((t) => ({
        date:
          (t.status === "paid" && t.payment_date ? t.payment_date : r.created_at) ?? null,
        supplier: r.supplier?.name ?? "",
        supplier_invoice: r.supplier_invoice_number ?? "",
        file_nos: r.sunshine_invoice_number ?? "",
        customer: r.customer?.name ?? "",
        curr: r.currency ?? "",
        amount: Number(t.amount),
      })),
  );
  // A ledger reads chronologically — oldest entry first.
  entries.sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
  return entries;
}

export async function exportBankLedgerToExcel(
  rows: DepositRequest[],
  filename: string,
  opts?: { unpaidOnly?: boolean },
): Promise<void> {
  await writeSheet(
    bankLedgerEntries(rows, opts).map((e) => ({
      "Date": e.date ? formatDate(e.date) : "",
      "Supplier": e.supplier,
      "Supplier Proforma Invoice #": e.supplier_invoice,
      "File Nos.": e.file_nos,
      "Customer": e.customer,
      "Curr": e.curr,
      "EURO/CNY": "",
      "Rate": "",
      "Debit": e.amount,
      "Credit": "",
      "BALANCE": "",
    })),
    filename,
    "Bank Ledger",
  );
}

export async function exportPendingReleaseToExcel(
  rows: PendingReleaseRow[], filename: string,
): Promise<void> {
  await writeSheet(
    rows.map((r) => ({
      "Request #": r.request_number,
      "Sunshine Invoice No.": r.sunshine_invoice_number ?? "",
      "Supplier": r.supplier_name,
      "Merchandiser": r.merchandiser_name ?? "",
      "Tranche": r.tranche_label,
      "Currency": r.currency ?? "",
      "Amount (to be released)": Number(r.amount),
      "Tentative Payment": r.tentative_payment_date ? formatDate(r.tentative_payment_date) : "",
    })),
    filename,
    "Yet to be Released",
  );
}

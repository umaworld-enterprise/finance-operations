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

// Bank-ledger format (4 Sep 2026, executive request): the exact ledger
// columns the executives keep in Excel. One row per tranche — a paid tranche
// is a ledger entry dated by its payment date with the amount in Debit; an
// unpaid tranche is an upcoming entry dated by the request date with Debit
// left empty. Voucher No., Rate, Credit and BALANCE are maintained manually
// in Excel (no such data in the system) and stay blank. The same entries
// feed both the Excel export and the on-screen Bank Ledger tab.
export interface BankLedgerEntry {
  date: string | null;
  supplier: string;
  file_nos: string;
  customer: string;
  curr: string;
  /** The "Currency" amount column (formerly EURO/CNY) — the tranche amount
   * in the request's own currency, so every currency is supported. */
  amount: number;
  /** Filled only for paid tranches. */
  debit: number | null;
}

export function bankLedgerEntries(rows: DepositRequest[]): BankLedgerEntry[] {
  const entries = rows.flatMap((r) =>
    (r.tranches ?? [])
      .filter((t) => t.status !== "rejected")
      .map((t) => {
        const paid = t.status === "paid";
        return {
          date: (paid && t.payment_date ? t.payment_date : r.created_at) ?? null,
          supplier: r.supplier?.name ?? "",
          file_nos: r.sunshine_invoice_number ?? "",
          customer: r.customer?.name ?? "",
          curr: r.currency ?? "",
          amount: Number(t.amount),
          debit: paid ? Number(t.amount) : null,
        };
      }),
  );
  // A ledger reads chronologically — oldest entry first.
  entries.sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
  return entries;
}

export async function exportBankLedgerToExcel(
  rows: DepositRequest[], filename: string,
): Promise<void> {
  await writeSheet(
    bankLedgerEntries(rows).map((e) => ({
      "Date": e.date ? formatDate(e.date) : "",
      "Supplier": e.supplier,
      "Voucher No.": "",
      "File Nos.": e.file_nos,
      "Customer": e.customer,
      "Curr": e.curr,
      "Currency": e.amount,
      "Rate": "",
      "Debit": e.debit ?? "",
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

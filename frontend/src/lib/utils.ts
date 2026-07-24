import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { UserRole } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
    }).format(amount);
  } catch {
    // Non-ISO codes (e.g. "OTHER") make Intl throw — fall back to a plain
    // formatted number with the code appended.
    return `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2 }).format(amount)} ${currency}`.trim();
  }
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// List tables show the Sunshine Invoice # as the client-facing identifier once
// accounts enters it; until then the ADT request number stands in. The ADT
// number remains the permanent identifier on detail pages, logs and exports.
export function requestDisplayNumber(req: {
  sunshine_invoice_number: string | null;
  request_number: string;
}): string {
  return req.sunshine_invoice_number || req.request_number;
}

// Client-side counterpart of the server `search` param — used by the
// non-paginated lists (accounts pending queue, HoM queue). Same fields.
export function requestMatchesSearch(
  req: {
    request_number: string;
    sunshine_invoice_number: string | null;
    supplier_invoice_number: string | null;
    supplier?: { name: string } | null;
    customer?: { name: string } | null;
  },
  term: string,
): boolean {
  const q = term.toLowerCase();
  return [
    req.request_number,
    req.sunshine_invoice_number,
    req.supplier_invoice_number,
    req.supplier?.name,
    req.customer?.name,
  ].some((v) => v?.toLowerCase().includes(q));
}

// Client-side counterpart of the server `sort` param — used by the
// non-paginated lists (accounts pending queue, HoM queue).
export function sortRequests<T extends { created_at: string; deposit_amount: number }>(
  reqs: T[],
  sort: string,
): T[] {
  const sorted = [...reqs];
  switch (sort) {
    case "oldest":
      return sorted.sort((a, b) => a.created_at.localeCompare(b.created_at));
    case "amount_desc":
      return sorted.sort((a, b) => Number(b.deposit_amount) - Number(a.deposit_amount));
    case "amount_asc":
      return sorted.sort((a, b) => Number(a.deposit_amount) - Number(b.deposit_amount));
    default: // newest
      return sorted.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }
}

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: "Super Admin",
  finance_admin: "Finance Admin",
  accounts_team: "Accounts Team",
  merchandiser: "Merchandiser",
  head_of_merchandiser: "Head of Merchandiser",
};

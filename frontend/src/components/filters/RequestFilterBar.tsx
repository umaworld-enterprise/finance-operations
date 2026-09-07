"use client";

// Dynamic filter module (4 Sep 2026, executive request): filter any request
// list by whichever columns matter — supplier, customer, vertical,
// merchandiser, currency, request-date range. "Add filter" opens a field
// picker; each active filter renders as its own control with a remove ✕.
// The same RequestFilterValues object feeds GET /requests server-side and
// the client-side matcher below (for lists fetched un-paginated, like the
// pending queue).

import { useState } from "react";
import { FilterX, ListFilter, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useCustomers,
  useMerchandiserOptions,
  useSuppliers,
  useVerticals,
} from "@/hooks/useMasters";
import type { DepositRequest } from "@/types";

export interface RequestFilterValues {
  supplier_id?: string;
  customer_id?: string;
  vertical_id?: string;
  created_by?: string;
  currency?: string;
  date_from?: string;
  date_to?: string;
}

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CNY", "JPY", "SGD", "OTHER"];

type FieldKey = keyof RequestFilterValues | "date_range";

const FIELD_LABELS: Record<FieldKey, string> = {
  supplier_id: "Supplier",
  customer_id: "Customer",
  vertical_id: "Vertical",
  created_by: "Merchandiser",
  currency: "Currency",
  date_range: "Request date",
  date_from: "Request date", // never listed directly — lives in date_range
  date_to: "Request date",
};

/** Server params for useRequestsPaginated — drops empty values. */
export function filterParams(values: RequestFilterValues): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(values)) {
    if (v) out[k] = v;
  }
  return out;
}

/** Client-side matcher — for lists fetched without server pagination
 * (e.g. the Accounts pending queue). Mirrors the backend filters. */
export function matchesRequestFilters(req: DepositRequest, values: RequestFilterValues): boolean {
  if (values.supplier_id && req.supplier?.id !== values.supplier_id) return false;
  if (values.customer_id && req.customer?.id !== values.customer_id) return false;
  if (values.vertical_id && req.vertical?.id !== values.vertical_id) return false;
  if (values.created_by && req.created_by !== values.created_by) return false;
  if (values.currency && req.currency !== values.currency) return false;
  const created = (req.created_at ?? "").slice(0, 10);
  if (values.date_from && created && created < values.date_from) return false;
  if (values.date_to && created && created > values.date_to) return false;
  return true;
}

export function countActiveFilters(values: RequestFilterValues): number {
  return Object.values(values).filter(Boolean).length;
}

const selectCls =
  "flex h-8 rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring";

export function RequestFilterBar({
  values,
  onChange,
  showMerchandiser = false,
}: {
  values: RequestFilterValues;
  onChange: (values: RequestFilterValues) => void;
  /** Hidden on the merchandiser's own list — they only see their requests. */
  showMerchandiser?: boolean;
}) {
  // Which fields the user has ADDED (a field stays visible while empty so a
  // value can be picked; removing the chip clears its value).
  const [active, setActive] = useState<FieldKey[]>([]);

  const { data: suppliers = [] } = useSuppliers();
  const { data: customers = [] } = useCustomers();
  const { data: verticals = [] } = useVerticals();
  const { data: merchandisers = [] } = useMerchandiserOptions(showMerchandiser);

  const availableFields: FieldKey[] = [
    "supplier_id",
    "customer_id",
    "vertical_id",
    ...(showMerchandiser ? (["created_by"] as FieldKey[]) : []),
    "currency",
    "date_range",
  ];
  const addable = availableFields.filter((f) => !active.includes(f));

  const set = (patch: Partial<RequestFilterValues>) => onChange({ ...values, ...patch });

  const removeField = (field: FieldKey) => {
    setActive((prev) => prev.filter((f) => f !== field));
    if (field === "date_range") set({ date_from: undefined, date_to: undefined });
    else set({ [field]: undefined } as Partial<RequestFilterValues>);
  };

  const clearAll = () => {
    setActive([]);
    onChange({});
  };

  const chip = (field: FieldKey, control: React.ReactNode) => (
    <span
      key={field}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 pl-2 pr-1 py-1"
    >
      <span className="text-xs text-muted-foreground whitespace-nowrap">{FIELD_LABELS[field]}</span>
      {control}
      <button
        type="button"
        onClick={() => removeField(field)}
        aria-label={`Remove ${FIELD_LABELS[field]} filter`}
        className="p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-muted transition-colors"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </span>
  );

  const optionSelect = (
    field: "supplier_id" | "customer_id" | "vertical_id" | "created_by" | "currency",
    options: { value: string; label: string }[],
    placeholder: string,
  ) =>
    chip(
      field,
      <select
        value={values[field] ?? ""}
        onChange={(e) => set({ [field]: e.target.value || undefined } as Partial<RequestFilterValues>)}
        className={`${selectCls} max-w-52`}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>,
    );

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value=""
        onChange={(e) => {
          const field = e.target.value as FieldKey;
          if (field) setActive((prev) => [...prev, field]);
        }}
        aria-label="Add filter"
        className={`${selectCls} w-36`}
        disabled={addable.length === 0}
      >
        <option value="">
          {addable.length === 0 ? "All filters added" : "+ Add filter"}
        </option>
        {addable.map((f) => (
          <option key={f} value={f}>{FIELD_LABELS[f]}</option>
        ))}
      </select>

      {active.includes("supplier_id") &&
        optionSelect("supplier_id", suppliers.map((s) => ({ value: s.id, label: s.name })), "All suppliers")}
      {active.includes("customer_id") &&
        optionSelect("customer_id", customers.map((c) => ({ value: c.id, label: c.name })), "All customers")}
      {active.includes("vertical_id") &&
        optionSelect("vertical_id", verticals.map((v) => ({ value: v.id, label: v.name })), "All verticals")}
      {active.includes("created_by") &&
        optionSelect("created_by", merchandisers.map((m) => ({ value: m.id, label: m.full_name })), "All merchandisers")}
      {active.includes("currency") &&
        optionSelect("currency", CURRENCIES.map((c) => ({ value: c, label: c })), "All currencies")}
      {active.includes("date_range") &&
        chip(
          "date_range",
          <span className="inline-flex items-center gap-1">
            <input
              type="date"
              value={values.date_from ?? ""}
              onChange={(e) => set({ date_from: e.target.value || undefined })}
              className={selectCls}
              aria-label="Request date from"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={values.date_to ?? ""}
              onChange={(e) => set({ date_to: e.target.value || undefined })}
              className={selectCls}
              aria-label="Request date to"
            />
          </span>,
        )}

      {(active.length > 0 || countActiveFilters(values) > 0) && (
        <Button size="sm" variant="ghost" onClick={clearAll} className="gap-1 text-muted-foreground">
          <FilterX className="h-3.5 w-3.5" /> Clear filters
        </Button>
      )}
      {active.length === 0 && countActiveFilters(values) === 0 && (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <ListFilter className="h-3.5 w-3.5" /> Filter by supplier, customer, vertical
          {showMerchandiser ? ", merchandiser" : ""}, currency or date
        </span>
      )}
    </div>
  );
}

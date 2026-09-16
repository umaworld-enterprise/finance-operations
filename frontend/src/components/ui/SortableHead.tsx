"use client";

// Column-header sorting (16 Sep 2026, executive request): every data table
// gets ascending / descending toggles ON THE HEADER itself. Click cycles
// A→Z, Z→A, then back to the table's natural order. Plug in with:
//
//   const colSort = useColumnSortState();
//   const rows = sortByColumn(allRows, ACCESSORS, colSort.sort);
//   ...
//   <SortableHead label="Supplier" sortKey="supplier" state={colSort} />
//
// ACCESSORS is a module-level map of sortKey → value getter; strings sort
// case-insensitively (and numerically where digits appear), numbers sort
// numerically, and blank values always sink to the bottom.

import { useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type SortDirection = "asc" | "desc";

export interface ColumnSort {
  key: string;
  direction: SortDirection;
}

export interface ColumnSortState {
  sort: ColumnSort | null;
  toggle: (key: string) => void;
}

export type ColumnAccessors<T> = Record<
  string,
  (row: T) => string | number | null | undefined
>;

export function useColumnSortState(): ColumnSortState {
  const [sort, setSort] = useState<ColumnSort | null>(null);
  const toggle = (key: string) =>
    setSort((prev) => {
      if (prev?.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return null; // third click restores the table's natural order
    });
  return { sort, toggle };
}

/** Comparator for one column — blanks last regardless of direction. */
export function makeColumnCompare<T>(
  accessors: ColumnAccessors<T>,
  sort: ColumnSort,
): (a: T, b: T) => number {
  const get = accessors[sort.key];
  const dir = sort.direction === "asc" ? 1 : -1;
  return (a: T, b: T) => {
    if (!get) return 0;
    const va = get(a);
    const vb = get(b);
    const aBlank = va == null || va === "";
    const bBlank = vb == null || vb === "";
    if (aBlank && bBlank) return 0;
    if (aBlank) return 1;
    if (bBlank) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return (
      String(va).localeCompare(String(vb), undefined, {
        sensitivity: "base",
        numeric: true,
      }) * dir
    );
  };
}

/** Returns rows sorted by the active column, or the input order when none. */
export function sortByColumn<T>(
  rows: T[],
  accessors: ColumnAccessors<T>,
  sort: ColumnSort | null,
): T[] {
  if (!sort || !accessors[sort.key]) return rows;
  return [...rows].sort(makeColumnCompare(accessors, sort));
}

export function SortableHead({
  label,
  sortKey,
  state,
  className,
  align,
}: {
  /** Plain text or richer content (e.g. a label with a help tooltip). */
  label: React.ReactNode;
  sortKey: string;
  state: ColumnSortState;
  className?: string;
  align?: "left" | "right";
}) {
  const active = state.sort?.key === sortKey;
  const direction = active ? state.sort!.direction : null;
  return (
    <TableHead
      className={cn("cursor-pointer select-none", className)}
      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}
      onClick={() => state.toggle(sortKey)}
      title={typeof label === "string" ? `Sort by ${label}` : "Sort"}
    >
      <span
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap",
          align === "right" && "w-full justify-end",
          active && "text-foreground",
        )}
      >
        {label}
        {direction === "asc" ? (
          <ArrowUp className="h-3 w-3 shrink-0" />
        ) : direction === "desc" ? (
          <ArrowDown className="h-3 w-3 shrink-0" />
        ) : (
          <ArrowUpDown className="h-3 w-3 shrink-0 opacity-35" />
        )}
      </span>
    </TableHead>
  );
}

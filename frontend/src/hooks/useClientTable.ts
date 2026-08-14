"use client";

// Client-side search + sort + pagination for array-backed tables
// (10 Aug 2026: app-wide table controls). Server-paginated tables keep
// their own wiring; this hook covers every table that receives a plain
// array. Search/sort changes reset to page 1; the page clamps when the
// filtered set shrinks (e.g. rows removed by a background refetch).

import { useMemo, useState } from "react";

export interface ClientSortOption<T> {
  value: string;
  label: string;
  compare: (a: T, b: T) => number;
}

export function useClientTable<T>(
  rows: T[],
  options: {
    /** Values matched (case-insensitive, substring) by the search box. */
    searchHaystack: (row: T) => (string | null | undefined)[];
    sortOptions: ClientSortOption<T>[];
    pageSize?: number;
  },
) {
  const { searchHaystack, sortOptions, pageSize = 20 } = options;
  const [search, setSearchRaw] = useState("");
  const [sort, setSortRaw] = useState(sortOptions[0]?.value ?? "");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    let out = rows;
    if (term) {
      out = rows.filter((row) =>
        searchHaystack(row).some((v) => v?.toLowerCase().includes(term)),
      );
    }
    const sorter = sortOptions.find((o) => o.value === sort);
    if (sorter) out = [...out].sort(sorter.compare);
    return out;
    // searchHaystack/sortOptions are stable per call site (defined inline
    // with constant behaviour) — rows/search/sort drive recomputation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, search, sort]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const visible = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return {
    visible,
    total,
    totalPages,
    pageSize,
    page: safePage,
    setPage,
    search,
    setSearch: (value: string) => {
      setSearchRaw(value);
      setPage(1);
    },
    sort,
    setSort: (value: string) => {
      setSortRaw(value);
      setPage(1);
    },
    sortOptions,
  };
}

// Comparator helpers shared by the call sites.
export const byString = <T,>(get: (row: T) => string | null | undefined, desc = false) =>
  (a: T, b: T) => {
    const cmp = (get(a) ?? "").localeCompare(get(b) ?? "");
    return desc ? -cmp : cmp;
  };

export const byNumber = <T,>(get: (row: T) => number | null | undefined, desc = false) =>
  (a: T, b: T) => {
    const cmp = (get(a) ?? 0) - (get(b) ?? 0);
    return desc ? -cmp : cmp;
  };

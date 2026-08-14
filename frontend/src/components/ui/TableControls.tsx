"use client";

// Search box + sort dropdown for client-side tables (pairs with
// useClientTable; render <Pagination> below the table separately).

import { SearchInput } from "@/components/ui/SearchInput";

export function TableControls({
  search,
  onSearch,
  sort,
  onSort,
  sortOptions,
  placeholder = "Search…",
}: {
  search: string;
  onSearch: (value: string) => void;
  sort: string;
  onSort: (value: string) => void;
  sortOptions: { value: string; label: string }[];
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col sm:flex-row gap-2 mb-3">
      <SearchInput value={search} onChange={onSearch} placeholder={placeholder} className="sm:max-w-xs flex-1" />
      {sortOptions.length > 0 && (
        <select
          value={sort}
          onChange={(e) => onSort(e.target.value)}
          aria-label="Sort"
          className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring sm:w-52"
        >
          {sortOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
    </div>
  );
}

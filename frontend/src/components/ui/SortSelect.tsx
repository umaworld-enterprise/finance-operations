"use client";

import { ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type RequestSort = "newest" | "oldest" | "amount_desc" | "amount_asc";

export const SORT_OPTIONS: { value: RequestSort; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "amount_desc", label: "Largest amount first" },
  { value: "amount_asc", label: "Smallest amount first" },
];

interface Props {
  value: RequestSort;
  onChange: (value: RequestSort) => void;
  className?: string;
}

/** Sort dropdown paired with the request-list SearchInput. */
export function SortSelect({ value, onChange, className }: Props) {
  return (
    <div className={cn("relative", className)}>
      <ArrowUpDown className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as RequestSort)}
        aria-label="Sort requests"
        className="h-9 rounded-lg border border-input bg-background pl-9 pr-8 text-sm text-foreground appearance-none focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 w-full"
      >
        {SORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

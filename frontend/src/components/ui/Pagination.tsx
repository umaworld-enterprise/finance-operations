"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  function pageNumbers(): (number | "…")[] {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const pages: (number | "…")[] = [1];
    if (page > 3) pages.push("…");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
    if (page < totalPages - 2) pages.push("…");
    pages.push(totalPages);
    return pages;
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-1 py-3 border-t border-border">
      <p className="text-xs text-muted-foreground tabular-nums">
        Showing <span className="font-medium text-foreground">{from.toLocaleString()}–{to.toLocaleString()}</span>{" "}
        of <span className="font-medium text-foreground">{total.toLocaleString()}</span> records
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page === 1}
          className="inline-flex items-center gap-1 px-3 py-2.5 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors touch-manipulation min-h-[44px]"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> Prev
        </button>
        {pageNumbers().map((p, i) =>
          p === "…" ? (
            <span key={`ellipsis-${i}`} className="px-1 text-xs text-muted-foreground">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onChange(p as number)}
              className={cn(
                "min-w-[40px] min-h-[44px] px-2 rounded-lg text-xs font-medium transition-colors touch-manipulation",
                p === page
                  ? "bg-foreground text-background"
                  : "border border-border text-muted-foreground hover:text-foreground hover:bg-muted",
              )}
            >
              {p}
            </button>
          ),
        )}
        <button
          onClick={() => onChange(page + 1)}
          disabled={page === totalPages}
          className="inline-flex items-center gap-1 px-3 py-2.5 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors touch-manipulation min-h-[44px]"
        >
          Next <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

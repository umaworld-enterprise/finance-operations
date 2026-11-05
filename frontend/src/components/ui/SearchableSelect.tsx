"use client";

// Type-to-search picker (5 Nov 2026, executive request): the Modify Request
// file list had grown long enough that a plain <select> was unusable. Typing
// filters the options; with the box empty it shows the most recent ones, so
// the common case needs no typing at all.

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SearchableOption {
  value: string;
  /** Shown in the input once chosen, and matched against while typing. */
  label: string;
  /** Second line in the list — also searched. */
  hint?: string;
}

export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "Search…",
  emptyMessage = "No matches.",
  recentCount = 15,
  id,
  disabled,
}: {
  options: SearchableOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyMessage?: string;
  /** How many to show before the user types anything. */
  recentCount?: number;
  id?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const selected = options.find((o) => o.value === value) ?? null;

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options.slice(0, recentCount);
    return options
      .filter(
        (o) =>
          o.label.toLowerCase().includes(q) || (o.hint ?? "").toLowerCase().includes(q),
      )
      .slice(0, 50);
  }, [options, query, recentCount]);

  // Clicking anywhere else closes the list and restores the chosen label.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const choose = (v: string) => {
    onChange(v);
    setOpen(false);
    setQuery("");
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { setOpen(true); return; }
      setActive((i) => {
        const next = e.key === "ArrowDown" ? i + 1 : i - 1;
        return Math.max(0, Math.min(next, matches.length - 1));
      });
    } else if (e.key === "Enter" && open && matches[active]) {
      e.preventDefault();
      choose(matches[active].value);
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  };

  return (
    <div ref={boxRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          disabled={disabled}
          value={open ? query : selected?.label ?? ""}
          placeholder={selected ? selected.label : placeholder}
          onFocus={() => { setOpen(true); setActive(0); }}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
          onKeyDown={onKeyDown}
          className="flex h-9 w-full rounded-md border border-input bg-background pl-8 pr-14 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
        />
        <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
          {selected && !disabled && (
            <button
              type="button"
              aria-label="Clear selection"
              onClick={() => { onChange(""); setQuery(""); setOpen(false); }}
              className="p-1 rounded text-muted-foreground hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-72 overflow-y-auto rounded-md border border-border bg-popover shadow-lg">
          {matches.length === 0 ? (
            <p className="px-3 py-2.5 text-xs text-muted-foreground">{emptyMessage}</p>
          ) : (
            <>
              {!query.trim() && options.length > matches.length && (
                <p className="px-3 pt-2 pb-1 text-[11px] text-muted-foreground">
                  Most recent {matches.length} of {options.length} — type to search them all
                </p>
              )}
              {matches.map((o, i) => (
                <button
                  key={o.value}
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(o.value)}
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm flex items-start gap-2",
                    i === active ? "bg-muted" : "hover:bg-muted/60",
                  )}
                >
                  <Check
                    className={cn(
                      "h-3.5 w-3.5 mt-0.5 shrink-0",
                      o.value === value ? "opacity-100 text-primary" : "opacity-0",
                    )}
                  />
                  <span className="min-w-0">
                    <span className="block font-mono text-xs font-semibold truncate">{o.label}</span>
                    {o.hint && (
                      <span className="block text-[11px] text-muted-foreground truncate">{o.hint}</span>
                    )}
                  </span>
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

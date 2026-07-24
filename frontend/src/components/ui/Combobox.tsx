"use client";

import * as React from "react";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  disabled?: boolean;
  allowFreeText?: boolean;
  className?: string;
  id?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}

export function Combobox({
  value,
  onChange,
  options,
  placeholder = "Search or select…",
  disabled = false,
  allowFreeText = true,
  className,
  id,
  "aria-invalid": ariaInvalid,
  "aria-describedby": ariaDescribedBy,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [highlighted, setHighlighted] = React.useState(0);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listRef = React.useRef<HTMLUListElement>(null);

  // When the external value changes (e.g. form reset), sync the input display
  React.useEffect(() => {
    if (!open) setQuery(value ?? "");
  }, [value, open]);

  const filtered = React.useMemo(() => {
    if (!query.trim()) return options.slice(0, 50);
    const q = query.toLowerCase();
    return options.filter((o) => o.toLowerCase().includes(q)).slice(0, 50);
  }, [query, options]);

  // Reset highlight whenever filtered list changes
  React.useEffect(() => {
    setHighlighted(0);
  }, [filtered]);

  // Scroll highlighted item into view
  React.useEffect(() => {
    if (!listRef.current) return;
    const item = listRef.current.children[highlighted] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlighted]);

  // Click outside → close and restore value
  React.useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery(value ?? "");
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [value]);

  function handleFocus() {
    setQuery("");
    setOpen(true);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    setOpen(true);
  }

  function select(option: string) {
    onChange(option);
    setQuery(option);
    setOpen(false);
    inputRef.current?.blur();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter") { setOpen(true); e.preventDefault(); }
      return;
    }
    const total = filtered.length + (allowFreeText && query && !filtered.includes(query) ? 1 : 0);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlighted((h) => Math.min(h + 1, total - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[highlighted] !== undefined) {
        select(filtered[highlighted]);
      } else if (allowFreeText && query.trim()) {
        select(query.trim());
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery(value ?? "");
    }
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange("");
    setQuery("");
    setOpen(false);
    inputRef.current?.focus();
  }

  const showFreeTextOption =
    allowFreeText && query.trim() && !filtered.some((o) => o.toLowerCase() === query.toLowerCase());

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <div className="relative">
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-invalid={ariaInvalid}
          aria-describedby={ariaDescribedBy}
          autoComplete="off"
          disabled={disabled}
          placeholder={placeholder}
          value={open ? query : (value ?? "")}
          onFocus={handleFocus}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          className={cn(
            "flex h-9 w-full rounded-lg border border-input bg-background px-3 py-2 pr-16 text-sm text-foreground ring-offset-background transition-colors",
            "placeholder:text-muted-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
            ariaInvalid && "border-destructive focus-visible:ring-destructive"
          )}
        />
        <div className="absolute inset-y-0 right-0 flex items-center pr-2 gap-0.5 pointer-events-none">
          {value && !disabled && (
            <button
              type="button"
              tabIndex={-1}
              onPointerDown={clear}
              className="pointer-events-auto p-0.5 rounded text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Clear"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform pointer-events-none",
              open && "rotate-180"
            )}
          />
        </div>
      </div>

      {open && (
        <ul
          ref={listRef}
          role="listbox"
          className={cn(
            "absolute z-50 mt-1 w-full max-h-60 overflow-auto rounded-lg border border-border bg-popover shadow-md",
            "text-sm text-popover-foreground py-1"
          )}
        >
          {filtered.length === 0 && !showFreeTextOption && (
            <li className="px-3 py-2 text-muted-foreground select-none">No matches found.</li>
          )}
          {filtered.map((option, i) => (
            <li
              key={option}
              role="option"
              aria-selected={option === value}
              onPointerDown={(e) => { e.preventDefault(); select(option); }}
              className={cn(
                "px-3 py-2 cursor-pointer select-none",
                i === highlighted ? "bg-accent text-accent-foreground" : "hover:bg-accent/60",
                option === value && "font-medium"
              )}
            >
              {option}
            </li>
          ))}
          {showFreeTextOption && (
            <li
              role="option"
              aria-selected={false}
              onPointerDown={(e) => { e.preventDefault(); select(query.trim()); }}
              className={cn(
                "px-3 py-2 cursor-pointer select-none text-muted-foreground italic",
                highlighted === filtered.length ? "bg-accent text-accent-foreground" : "hover:bg-accent/60"
              )}
            >
              Use &ldquo;{query.trim()}&rdquo; as entered
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

"use client";

// Excel export button for request tables (2 Sep 2026) — exports exactly the
// rows the caller passes (i.e. the table's current, search-filtered view).
// 4 Sep 2026: when the caller also provides a bank-ledger export, the button
// opens a two-option menu: Bank Ledger format or the standard export.

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ExportButton({
  onExport,
  onExportLedger,
  count,
}: {
  /** Performs the standard export (lazy-loads SheetJS). */
  onExport: () => Promise<void>;
  /** Bank-ledger export — providing it turns the button into a 2-option menu. */
  onExportLedger?: () => Promise<void>;
  /** How many rows the export will carry — disabled at 0. */
  count: number;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close the menu on any click outside it.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const run = async (fn: () => Promise<void>) => {
    setOpen(false);
    setBusy(true);
    try {
      await fn();
      toast.success(`Exported ${count} row${count === 1 ? "" : "s"} to Excel.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!onExportLedger) {
    return (
      <Button
        size="sm"
        variant="outline"
        disabled={busy || count === 0}
        onClick={() => void run(onExport)}
        className="gap-1.5"
      >
        <FileDown className="h-3.5 w-3.5" />
        {busy ? "Exporting…" : "Export Excel"}
      </Button>
    );
  }

  return (
    <div ref={wrapRef} className="relative inline-block">
      <Button
        size="sm"
        variant="outline"
        disabled={busy || count === 0}
        onClick={() => setOpen((v) => !v)}
        className="gap-1.5"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <FileDown className="h-3.5 w-3.5" />
        {busy ? "Exporting…" : "Export Excel"}
        <ChevronDown className="h-3.5 w-3.5" />
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-52 rounded-md border border-border bg-popover p-1 shadow-md"
        >
          <button
            role="menuitem"
            className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => void run(onExportLedger)}
          >
            Export in Bank Ledger
          </button>
          <button
            role="menuitem"
            className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => void run(onExport)}
          >
            Export
          </button>
        </div>
      )}
    </div>
  );
}

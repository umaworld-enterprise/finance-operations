"use client";

// Excel export button for request tables (2 Sep 2026) — exports exactly the
// rows the caller passes (i.e. the table's current, search-filtered view).

import { useState } from "react";
import { toast } from "sonner";
import { FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ExportButton({
  onExport,
  count,
}: {
  /** Performs the export (lazy-loads SheetJS). */
  onExport: () => Promise<void>;
  /** How many rows the export will carry — disabled at 0. */
  count: number;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy || count === 0}
      onClick={async () => {
        setBusy(true);
        try {
          await onExport();
          toast.success(`Exported ${count} row${count === 1 ? "" : "s"} to Excel.`);
        } catch (err: unknown) {
          toast.error(err instanceof Error ? err.message : "Export failed.");
        } finally {
          setBusy(false);
        }
      }}
      className="gap-1.5"
    >
      <FileDown className="h-3.5 w-3.5" />
      {busy ? "Exporting…" : "Export Excel"}
    </Button>
  );
}

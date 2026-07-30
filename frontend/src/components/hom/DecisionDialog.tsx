"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  open: boolean;
  title: string;
  description?: string;
  placeholder: string;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onClose: () => void;
  onConfirm: (remarks: string) => void;
}

/** HoM approve/reject dialog — the reason is mandatory for both decisions,
 * so Confirm stays disabled until a non-blank reason is entered. */
export function DecisionDialog({
  open,
  title,
  description,
  placeholder,
  confirmLabel,
  destructive,
  busy,
  onClose,
  onConfirm,
}: Props) {
  const [remarks, setRemarks] = useState("");
  if (!open) return null;

  const close = () => {
    setRemarks("");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-card rounded-xl border border-border shadow-lg p-6 w-full max-w-md space-y-4">
        <h3 className="font-semibold text-foreground">{title}</h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-foreground">
            Reason<span className="ml-0.5" aria-hidden="true">*</span>
          </label>
          <textarea
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            rows={3}
            placeholder={placeholder}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            required
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={close} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            size="sm"
            disabled={remarks.trim() === "" || busy}
            onClick={() => {
              onConfirm(remarks.trim());
              setRemarks("");
              onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

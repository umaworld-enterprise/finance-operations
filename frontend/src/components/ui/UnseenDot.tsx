"use client";

// Seen/unseen marker (23 Sep 2026, executive request): a red dot on any file
// that changed since this user last opened it. Opening the request clears it.

import { cn } from "@/lib/utils";

export function UnseenDot({ show, className }: { show: boolean; className?: string }) {
  if (!show) return null;
  return (
    <span
      title="Updated since you last opened this file"
      aria-label="Unseen changes"
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full bg-red-600 ring-2 ring-red-600/20",
        className,
      )}
    />
  );
}

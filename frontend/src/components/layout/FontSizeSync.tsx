"use client";

import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { applyFontSize, getStoredFontSize, storeFontSize } from "@/lib/fontSize";

/**
 * Syncs the server-side font size preference (users.font_size) into
 * localStorage + the document root. localStorage is what the pre-hydration
 * inline script in layout.tsx reads, so the next load has no flash.
 */
export function FontSizeSync() {
  const { user } = useAuth();

  useEffect(() => {
    const serverSize = user?.font_size;
    if (!serverSize) return;
    if (serverSize !== getStoredFontSize()) {
      storeFontSize(serverSize);
      applyFontSize(serverSize);
    }
  }, [user?.font_size]);

  return null;
}

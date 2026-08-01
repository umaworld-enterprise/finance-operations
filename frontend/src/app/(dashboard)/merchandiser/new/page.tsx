"use client";

// The Supplier Advance Payment Request form moved into the Merchandiser
// Queue as a collapsible section (Aug 2026 batch, item 2.2). This route stays
// as a redirect so existing bookmarks keep working; ?new=1 auto-expands it.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingScreen } from "@/components/ui/LoadingScreen";

export default function NewRequestRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/merchandiser?new=1");
  }, [router]);
  return <LoadingScreen message="Opening the request form…" />;
}

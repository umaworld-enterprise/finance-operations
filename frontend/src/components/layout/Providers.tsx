"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Toaster } from "sonner";
import { AuthProvider } from "@/contexts/auth-context";

// Devtools stay out of the production bundle entirely.
const ReactQueryDevtools =
  process.env.NODE_ENV === "development"
    ? dynamic(() =>
        import("@tanstack/react-query-devtools").then((m) => m.ReactQueryDevtools)
      )
    : () => null;

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // 60 s before data counts as stale (was 5 min) — the UAT change
            // note (Aug 2026, item 4) asked for auto-reload across the app;
            // workflow queries additionally poll every 30 s in their hooks.
            staleTime: 60 * 1000,
            // Keep data in memory for 30 minutes after all components unmount.
            // Navigating back to a page is instant — stale data shows first,
            // then refreshes in the background.
            gcTime: 30 * 60 * 1000,
            // Returning to the app window re-fetches stale queries — the
            // cheapest way to make cross-user changes visible (item 4).
            refetchOnWindowFocus: true,
            // Re-fetch on mount when stale so navigating to a page shows
            // fresh data (previously never re-fetched on mount).
            refetchOnMount: true,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
        <Toaster position="bottom-right" richColors />
        <ReactQueryDevtools initialIsOpen={false} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

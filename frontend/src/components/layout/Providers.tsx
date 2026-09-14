"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
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
  // 2 Sep 2026: scrolling the page while a number input has focus must not
  // change its value — blur the input the moment the wheel moves, app-wide.
  useEffect(() => {
    const onWheel = () => {
      const el = document.activeElement;
      if (el instanceof HTMLInputElement && el.type === "number") el.blur();
    };
    document.addEventListener("wheel", onWheel, { passive: true });
    return () => document.removeEventListener("wheel", onWheel);
  }, []);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Near-live app (19 Aug 2026, executive feedback: cross-user
            // changes must show without a manual refresh): data counts as
            // stale after 10 s and EVERY query polls every 15 s while its
            // page is visible. Workflow-critical hooks poll faster (10 s)
            // in their own files.
            staleTime: 10 * 1000,
            refetchInterval: 15 * 1000,
            // Hidden tabs don't poll (default) — the focus refetch below
            // catches up the moment the user returns.
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

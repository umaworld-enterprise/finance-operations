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
            // Keep cached data for 5 minutes before considering it stale.
            // Prevents background refetches during normal navigation.
            staleTime: 5 * 60 * 1000,
            // Keep data in memory for 30 minutes after all components unmount.
            // Navigating back to a page is instant — no re-fetch needed.
            gcTime: 30 * 60 * 1000,
            // Never re-fetch just because the user switched browser windows.
            // This was the biggest source of spurious network calls.
            refetchOnWindowFocus: false,
            // Don't re-fetch on component mount if data is within staleTime.
            // The data shown on navigation is always the most recently fetched
            // version; a manual invalidation or mutation triggers the next fetch.
            refetchOnMount: false,
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

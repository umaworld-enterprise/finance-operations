"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { SidebarContext } from "@/components/layout/sidebar-context";
import { PushPrompt } from "@/components/notifications/PushPrompt";
import { useAuth } from "@/hooks/useAuth";
import ErrorBoundary from "@/components/ErrorBoundary";

// BIChat pulls in react-markdown (~40KB gzipped) — load it lazily so it
// doesn't weigh down every dashboard page's initial bundle.
const BIChat = dynamic(
  () => import("@/components/ai/BIChat").then((m) => m.BIChat),
  { ssr: false }
);

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && user && user.onboarding_completed === false) {
      router.replace("/onboarding");
    }
  }, [user, loading, router]);

  // Block rendering until auth resolves and onboarding is confirmed complete.
  // This prevents authenticated-but-incomplete users from seeing the dashboard
  // even briefly before the redirect fires.
  if (loading || !user || user.onboarding_completed === false) {
    return null;
  }

  return (
    <SidebarContext.Provider value={{ open: sidebarOpen, setOpen: setSidebarOpen }}>
      <ErrorBoundary resetKey={pathname}>
        <div className="flex min-h-screen bg-background">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:z-[60] focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-primary focus:text-primary-foreground focus:text-sm"
          >
            Skip to content
          </a>
          <Sidebar />
          <div id="main-content" className="flex-1 flex flex-col overflow-hidden min-w-0">
            {children}
          </div>
          <BIChat />
          <PushPrompt />
        </div>
      </ErrorBoundary>
    </SidebarContext.Provider>
  );
}

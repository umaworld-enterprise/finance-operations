"use client";

// Sidebar "new since you last looked" badges (29 Sep 2026, executive
// request). The count is what arrived or changed in a section since the user
// last opened it; navigating to the section stamps it and the badge clears.

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import notificationService, { type SidebarCounts } from "@/services/notificationService";
import { useAuth } from "@/hooks/useAuth";

export const SIDEBAR_COUNTS_KEY = ["notifications", "sidebar-counts"] as const;

/** Sidebar href → section key the backend counts. */
export const SECTION_BY_HREF: Record<string, string> = {
  "/accounts": "accounts",
  "/hom": "hom",
  "/file-remarks": "file_remarks",
  "/merchandiser": "merchandiser",
};

export function useSidebarCounts(): SidebarCounts {
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: SIDEBAR_COUNTS_KEY,
    queryFn: notificationService.sidebarCounts,
    enabled: !!user,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
  return data ?? {};
}

/** Stamps the section as seen whenever the user lands on one of its pages. */
export function useMarkSectionViewed(pathname: string) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { mutate } = useMutation({
    mutationFn: (section: string) => notificationService.markSectionViewed(section),
    onSuccess: () => qc.invalidateQueries({ queryKey: SIDEBAR_COUNTS_KEY }),
  });
  // Detail routes count as visiting their section (/accounts/<id> → accounts).
  const section = Object.entries(SECTION_BY_HREF).find(
    ([href]) => pathname === href || pathname.startsWith(href + "/"),
  )?.[1];
  // Stamp once per section entry, not on every re-render.
  const stamped = useRef<string | null>(null);

  useEffect(() => {
    if (!user || !section || stamped.current === section) return;
    stamped.current = section;
    mutate(section);
  }, [user, section, mutate]);
}

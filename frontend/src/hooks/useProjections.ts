"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import projectionService, { type ProjectionSubmitItem } from "@/services/projectionService";

export const PROJECTIONS_KEY = ["projections"] as const;

export function useProjectionStatus(enabled = true) {
  return useQuery({
    queryKey: [...PROJECTIONS_KEY, "status"],
    queryFn: projectionService.status,
    enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useProjectionDashboard(year: number, month: number) {
  return useQuery({
    queryKey: [...PROJECTIONS_KEY, "dashboard", year, month],
    queryFn: () => projectionService.dashboard(year, month),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useSubmitProjections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ year, month, items }: { year: number; month: number; items: ProjectionSubmitItem[] }) =>
      projectionService.submit(year, month, items),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...PROJECTIONS_KEY] }),
  });
}

/** Advisory reminder for the request form (5 Nov 2026). Cheap and shared —
 * fetched once for every vertical rather than per selection. */
export function useProjectionReminders(enabled = true) {
  return useQuery({
    queryKey: [...PROJECTIONS_KEY, "reminders"],
    queryFn: projectionService.reminders,
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** The confirmation form's 3-month trend for one vertical. */
export function useProjectionTrend(
  verticalId: string | null,
  year?: number,
  month?: number,
) {
  return useQuery({
    queryKey: [...PROJECTIONS_KEY, "trend", verticalId, year, month],
    queryFn: () => projectionService.trend(verticalId as string, year, month),
    enabled: !!verticalId,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useProjectionSettings() {
  return useQuery({
    queryKey: [...PROJECTIONS_KEY, "settings"],
    queryFn: projectionService.settings,
    staleTime: 60_000,
  });
}

export function useSetProjectionLock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => projectionService.setLockEnabled(enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...PROJECTIONS_KEY] }),
  });
}

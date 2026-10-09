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

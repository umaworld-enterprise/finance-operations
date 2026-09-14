"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { analyticsService, type AnalyticsFilters } from "@/services/analyticsService";
import type { NpaResponse } from "@/types";

const STALE = 5 * 60 * 1000;
const GC    = 30 * 60 * 1000;

export function useAnalyticsSummary(filters?: AnalyticsFilters) {
  return useQuery({
    queryKey: ["analytics", "summary", filters],
    queryFn: () => analyticsService.getSummary(filters),
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useAnalyticsSnapshots(filters?: AnalyticsFilters) {
  return useQuery({
    queryKey: ["analytics", "snapshots", filters],
    queryFn: () => analyticsService.getSnapshots(filters),
    staleTime: STALE,
    gcTime: GC,
    // Large payload — show stale data immediately rather than blanking the page
    // while the background refetch completes.
    placeholderData: keepPreviousData,
  });
}

export function useWeeklyDeposits(enabled = true) {
  return useQuery({
    queryKey: ["analytics", "weekly-deposits"],
    queryFn: analyticsService.getWeeklyDeposits,
    enabled,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useShipments(enabled = true) {
  return useQuery({
    queryKey: ["analytics", "shipments"],
    queryFn: analyticsService.getShipments,
    enabled,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useNpa() {
  return useQuery<NpaResponse>({
    queryKey: ["analytics", "npa"],
    queryFn: analyticsService.getNpa,
    staleTime: STALE,
    gcTime: GC,
  });
}

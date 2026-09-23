"use client";

// Seen/unseen red dot (23 Sep 2026, executive request): which requests have
// changed since THIS user last opened them. Returned as a Set so tables can
// test membership per row without re-scanning an array.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import requestService from "@/services/requestService";
import { useAuth } from "@/hooks/useAuth";

export const UNSEEN_KEY = ["requests", "unseen"] as const;

export function useUnseenRequests(enabled = true) {
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: UNSEEN_KEY,
    queryFn: requestService.unseenIds,
    enabled: enabled && !!user,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
  return new Set(data ?? []);
}

/** Clears one request's dot — fired when the user opens it. */
export function useMarkRequestViewed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => requestService.markViewed(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: UNSEEN_KEY }),
  });
}

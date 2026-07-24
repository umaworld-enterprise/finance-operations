"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import notificationService from "@/services/notificationService";
import { useAuth } from "@/hooks/useAuth";

export function useNotifications() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationService.list(1, 20),
    enabled: !!user,
    refetchInterval: 30_000,
  });
}

export function useNotificationsPaginated(page: number, pageSize: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["notifications", "page", page, pageSize],
    queryFn: () => notificationService.list(page, pageSize),
    enabled: !!user,
    refetchInterval: 30_000,
  });
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[] | null) => notificationService.markRead(ids),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

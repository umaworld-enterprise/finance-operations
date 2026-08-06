"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import fileRemarkService, { type CreateFileRemarkPayload } from "@/services/fileRemarkService";

export const FILE_REMARKS_KEY = ["file-remarks"] as const;

export function useFileRemarks(params?: { status?: "open" | "resolved"; request_id?: string }) {
  return useQuery({
    queryKey: [...FILE_REMARKS_KEY, params ?? {}],
    queryFn: () => fileRemarkService.list(params),
    staleTime: 30_000,
  });
}

export function useCreateFileRemark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateFileRemarkPayload) => fileRemarkService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FILE_REMARKS_KEY] }),
  });
}

export function useResolveFileRemark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, responseNote }: { id: string; responseNote?: string }) =>
      fileRemarkService.resolve(id, responseNote),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FILE_REMARKS_KEY] }),
  });
}

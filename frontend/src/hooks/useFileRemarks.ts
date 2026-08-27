"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import fileRemarkService, { type CreateFileRemarkPayload } from "@/services/fileRemarkService";

export const FILE_REMARKS_KEY = ["file-remarks"] as const;

export function useFileRemarks(params?: {
  status?: "open" | "approved" | "rejected" | "resolved";
  request_id?: string;
}) {
  return useQuery({
    queryKey: [...FILE_REMARKS_KEY, params ?? {}],
    queryFn: () => fileRemarkService.list(params),
    staleTime: 30_000,
    // Auto-reload (UAT Aug 2026, item 4): new remarks and decisions appear
    // without a manual refresh.
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
}

export function useSelectableFiles(enabled: boolean) {
  return useQuery({
    queryKey: [...FILE_REMARKS_KEY, "selectable-files"],
    queryFn: fileRemarkService.selectableFiles,
    enabled,
    refetchInterval: 10_000,
  });
}

export function useCreateFileRemark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateFileRemarkPayload) => fileRemarkService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FILE_REMARKS_KEY] }),
  });
}

// Approve (processed) or reject an open remark (UAT Aug 2026, item 14).
export function useDecideFileRemark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      decision,
      responseNote,
    }: {
      id: string;
      decision: "approved" | "rejected";
      responseNote?: string;
    }) => fileRemarkService.decide(id, decision, responseNote),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FILE_REMARKS_KEY] }),
  });
}

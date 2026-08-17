"use client";

// Banking module (Aug 2026). Lists and details poll faster while an
// extraction is still processing, then settle to the normal cadence.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import bankStatementService from "@/services/bankStatementService";
import type { BankStatement, BankStatementDetail } from "@/types";

export const BANK_STATEMENTS_KEY = ["bank-statements"] as const;

export function useBankStatements() {
  return useQuery({
    queryKey: [...BANK_STATEMENTS_KEY],
    queryFn: bankStatementService.list,
    staleTime: 15_000,
    refetchInterval: (query) => {
      const rows = query.state.data as BankStatement[] | undefined;
      return rows?.some((s) => s.status === "processing") ? 5_000 : 30_000;
    },
    refetchOnWindowFocus: true,
  });
}

export function useBankStatement(id: string) {
  return useQuery({
    queryKey: [...BANK_STATEMENTS_KEY, id],
    queryFn: () => bankStatementService.get(id),
    enabled: !!id,
    staleTime: 15_000,
    refetchInterval: (query) => {
      const row = query.state.data as BankStatementDetail | undefined;
      return row?.status === "processing" ? 5_000 : 60_000;
    },
    refetchOnWindowFocus: true,
  });
}

export function useUploadBankStatement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => bankStatementService.upload(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...BANK_STATEMENTS_KEY] }),
  });
}

export function useDeleteBankStatement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => bankStatementService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...BANK_STATEMENTS_KEY] }),
  });
}

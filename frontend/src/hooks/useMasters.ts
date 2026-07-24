"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import masterService, {
  type FlagSupplierPayload,
  type CreateUserPayload,
  type UpdateUserPayload,
} from "@/services/masterService";

const STALE = 5 * 60 * 1000;
const GC    = 30 * 60 * 1000;  // master data changes rarely; keep in memory 30 min

export function usePaymentTerms() {
  return useQuery({
    queryKey: ["payment-terms"],
    queryFn: masterService.getPaymentTerms,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useAllPaymentTerms() {
  return useQuery({
    queryKey: ["payment-terms-all"],
    queryFn: masterService.getAllPaymentTerms,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useCreatePaymentTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ label, sort_order }: { label: string; sort_order?: number }) =>
      masterService.createPaymentTerm(label, sort_order),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payment-terms"] });
      qc.invalidateQueries({ queryKey: ["payment-terms-all"] });
    },
  });
}

export function useUpdatePaymentTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { label?: string; is_active?: boolean; sort_order?: number } }) =>
      masterService.updatePaymentTerm(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payment-terms"] });
      qc.invalidateQueries({ queryKey: ["payment-terms-all"] });
    },
  });
}

export function useDeletePaymentTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => masterService.deletePaymentTerm(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payment-terms"] });
      qc.invalidateQueries({ queryKey: ["payment-terms-all"] });
    },
  });
}

export function useVerticals() {
  return useQuery({
    queryKey: ["verticals"],
    queryFn: masterService.getVerticals,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useCustomers() {
  return useQuery({
    queryKey: ["customers"],
    queryFn: masterService.getCustomers,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useSuppliers() {
  return useQuery({
    queryKey: ["suppliers"],
    queryFn: masterService.getSuppliers,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useSupplierDefaultStatus(supplierId: string | null) {
  return useQuery({
    queryKey: ["supplier-default", supplierId],
    queryFn: () => masterService.checkSupplierDefault(supplierId!),
    enabled: !!supplierId,
    staleTime: STALE,
    gcTime: GC,
  });
}

export function useDefaultedSuppliers() {
  return useQuery({
    queryKey: ["defaulted-suppliers"],
    queryFn: masterService.getDefaultedSuppliers,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useFlagSupplier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: FlagSupplierPayload) => masterService.flagSupplier(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["defaulted-suppliers"] });
      qc.invalidateQueries({ queryKey: ["suppliers"] });
    },
  });
}

export function useResolveDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: masterService.resolveDefaultFlag,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["defaulted-suppliers"] }),
  });
}

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: masterService.getUsers,
    staleTime: STALE,
    gcTime: GC,
    placeholderData: keepPreviousData,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateUserPayload) => masterService.createUser(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateUserPayload }) =>
      masterService.updateUser(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

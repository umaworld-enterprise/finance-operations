"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import requestService, {
  type CreateRequestPayload,
  type UpdateRequestPayload,
} from "@/services/requestService";
import type { DepositRequest, RequestStatus } from "@/types";

const STALE      = 5 * 60 * 1000;
const STALE_PAGED = 2 * 60 * 1000;
const GC         = 30 * 60 * 1000;
const POLL       = 30 * 1000;

export const REQUESTS_KEY = ["requests"] as const;

// Invalidate the request LIST queries without touching every open detail
// view. Invalidating the bare ["requests"] prefix refetched 6+ queries after
// every click — a visible refetch storm on polling dashboards.
function invalidateRequestLists(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, "paginated"] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, "pending-queue"] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, "hom-queue"] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, "my-activity"] });
  // The unpaginated list (useRequests) keys are ["requests", <params-object|undefined>]
  qc.invalidateQueries({
    predicate: (q) =>
      q.queryKey[0] === "requests" &&
      q.queryKey.length === 2 &&
      typeof q.queryKey[1] !== "string",
  });
}

// Optimistically flip a request's status in the detail cache so the UI
// responds instantly; onError rolls back, onSettled reconciles with server.
async function optimisticStatusFlip(
  qc: QueryClient,
  id: string,
  status: RequestStatus,
): Promise<{ previous: DepositRequest | undefined }> {
  await qc.cancelQueries({ queryKey: [...REQUESTS_KEY, id] });
  const previous = qc.getQueryData<DepositRequest>([...REQUESTS_KEY, id]);
  qc.setQueryData<DepositRequest>([...REQUESTS_KEY, id], (old) =>
    old ? { ...old, current_status: status } : old
  );
  return { previous };
}

export function useRequests(params?: Record<string, string>) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, params],
    queryFn: () => requestService.list(params),
    staleTime: STALE,
    gcTime: GC,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });
}

export function useRequestsPaginated(
  page: number,
  pageSize: number,
  params?: Record<string, string | string[]>,
) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, "paginated", page, pageSize, params],
    queryFn: () => requestService.listPaginated(page, pageSize, params),
    staleTime: STALE_PAGED,
    gcTime: GC,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });
}

export function usePendingQueue() {
  return useQuery({
    queryKey: [...REQUESTS_KEY, "pending-queue"],
    queryFn: requestService.pendingQueue,
    staleTime: STALE,
    gcTime: GC,
    refetchInterval: POLL,
    refetchOnWindowFocus: true,
  });
}

export function useRequest(id: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, id],
    queryFn: () => requestService.get(id),
    enabled: !!id,
    staleTime: 0,
    gcTime: GC,
  });
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRequestPayload) => requestService.create(data),
    onSuccess: () => invalidateRequestLists(qc),
  });
}

export function useUpdateRequest(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateRequestPayload) => requestService.update(id, data),
    onSuccess: () => {
      invalidateRequestLists(qc);
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, id] });
    },
  });
}

// Single mutation that accepts { id, action, remarks } — used by both merchandiser and accounts detail pages.
// Pass optimisticStatus (the status the action will produce for the acting
// role) to flip the detail view instantly instead of waiting for the server.
export function useRequestAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      action,
      remarks,
    }: {
      id: string;
      action: "hold" | "resume" | "cancel" | "reopen";
      remarks?: string;
      optimisticStatus?: RequestStatus;
    }) => {
      switch (action) {
        case "hold":   return requestService.hold(id, remarks);
        case "resume": return requestService.resume(id, remarks);
        case "cancel": return requestService.cancel(id, remarks);
        case "reopen": return requestService.reopen(id, remarks);
      }
    },
    onMutate: async ({ id, optimisticStatus }) => {
      if (!optimisticStatus) return { previous: undefined, id };
      const { previous } = await optimisticStatusFlip(qc, id, optimisticStatus);
      return { previous, id };
    },
    onError: (_err, { id }, context) => {
      if (context?.previous !== undefined) {
        qc.setQueryData([...REQUESTS_KEY, id], context.previous);
      }
    },
    onSettled: (_data, _err, { id }) => {
      invalidateRequestLists(qc);
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, id] });
    },
  });
}

export function usePayment(requestId: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, requestId, "payment"],
    queryFn: () => requestService.getPayment(requestId),
    enabled: !!requestId,
    staleTime: STALE,
    gcTime: GC,
  });
}

// useSavePayment / useProcessPayment were removed with the request-level
// Payment Details form (Aug 2026 follow-up) — payment details are captured
// per tranche, and the backend derives request-level payment_date/status
// when the final tranche is paid.

// Ship date has its own endpoint because it stays writable after the record is
// locked (it stops Cost of Fund accrual). Invalidate the request too — the
// analytics snapshot is recomputed server-side right after.
export function useSaveShipDate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, shipDate }: { requestId: string; shipDate: string }) =>
      requestService.saveShipDate(requestId, shipDate),
    onSuccess: (_, { requestId }) => {
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId] });
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId, "payment"] });
    },
  });
}


export function useUpdateRemarks(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (remarks: string) => requestService.updateRemarks(id, remarks),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, id] });
    },
  });
}

// ── Advance Payment Tranches ──────────────────────────────────────────────────

function invalidateRequestAndTranches(qc: QueryClient, requestId: string) {
  invalidateRequestLists(qc);
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId, "tranches"] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId, "audit"] });
  qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId, "tranches-modifiable"] });
}

export function useTranches(requestId: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, requestId, "tranches"],
    queryFn: () => requestService.listTranches(requestId),
    enabled: !!requestId,
    staleTime: 0,
    gcTime: GC,
  });
}

export function useUpdateTranche(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ trancheId, data }: { trancheId: string; data: { amount?: number; tentative_payment_date?: string } }) =>
      requestService.updateTranche(requestId, trancheId, data),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

// Merchandiser tranche management — allowed only while the request is pending
// and untouched by Accounts (Aug 2026 batch, item 2.3). Server-enforced;
// useTranchesModifiable mirrors the rule for the UI.

export function useTranchesModifiable(requestId: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, requestId, "tranches-modifiable"],
    queryFn: () => requestService.tranchesModifiable(requestId),
    enabled: !!requestId,
    staleTime: 0,
  });
}

export function useAddTranche(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { amount: number; tentative_payment_date: string }) =>
      requestService.addTranche(requestId, data),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

export function useDeleteTranche(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (trancheId: string) => requestService.deleteTranche(requestId, trancheId),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

// Accounts: per-tranche payment details + explicit mark-paid (Aug 2026,
// item 3.1 — the TT upload no longer auto-pays; paying requires the TT copy
// AND payment details, then an explicit click).

export function useUpdateTranchePaymentDetails(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      trancheId,
      data,
    }: {
      trancheId: string;
      data: {
        payment_date?: string;
        bank?: string;
        payment_reference_number?: string;
        accounts_remarks?: string;
      };
    }) => requestService.updateTranchePaymentDetails(requestId, trancheId, data),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

export function usePayTranche(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (trancheId: string) => requestService.payTranche(requestId, trancheId),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

export function useRejectTranche(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ trancheId, reason }: { trancheId: string; reason: string }) =>
      requestService.rejectTranche(requestId, trancheId, reason),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

export function useUploadTrancheTtCopy(requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ trancheId, file }: { trancheId: string; file: File }) =>
      requestService.uploadTrancheTtCopy(requestId, trancheId, file),
    onSuccess: () => invalidateRequestAndTranches(qc, requestId),
  });
}

export function useRequestAuditTrail(requestId: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, requestId, "audit"],
    queryFn: () => requestService.auditTrail(requestId),
    enabled: !!requestId,
    staleTime: 0,
    gcTime: GC,
  });
}

export function useRequestAdjustments(requestId: string) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, requestId, "adjustments"],
    queryFn: () => requestService.adjustments(requestId),
    enabled: !!requestId,
    staleTime: STALE,
    gcTime: GC,
  });
}

export function useFieldVisibility() {
  return useQuery({
    queryKey: ["field-visibility"],
    queryFn: () => requestService.myFieldVisibility(),
    staleTime: 5 * 60 * 1000,
    gcTime: GC,
  });
}

export function useMyActivity(limit = 50) {
  return useQuery({
    queryKey: [...REQUESTS_KEY, "my-activity", limit],
    queryFn: () => requestService.myActivity(limit),
    staleTime: 0,
    gcTime: GC,
    refetchInterval: POLL,
    refetchOnWindowFocus: true,
  });
}

export function useHomQueue() {
  return useQuery({
    queryKey: [...REQUESTS_KEY, "hom-queue"],
    queryFn: requestService.homQueue,
    staleTime: STALE,
    gcTime: GC,
    refetchInterval: POLL,
    refetchOnWindowFocus: true,
  });
}

export function useHomApprove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, remarks }: { id: string; remarks: string }) =>
      requestService.homApprove(id, remarks),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: [...REQUESTS_KEY, id] });
      const previous = qc.getQueryData<DepositRequest>([...REQUESTS_KEY, id]);
      qc.setQueryData<DepositRequest>([...REQUESTS_KEY, id], (old) =>
        old ? { ...old, current_status: "pending_payment" } : old
      );
      return { previous, id };
    },
    onError: (_err, { id }, context) => {
      if (context?.previous !== undefined) {
        qc.setQueryData([...REQUESTS_KEY, id], context.previous);
      }
    },
    onSettled: (_data, _err, { id }) => {
      invalidateRequestLists(qc);
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, id] });
    },
  });
}

export function useHomReject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, remarks }: { id: string; remarks: string }) =>
      requestService.homReject(id, remarks),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: [...REQUESTS_KEY, id] });
      const previous = qc.getQueryData<DepositRequest>([...REQUESTS_KEY, id]);
      qc.setQueryData<DepositRequest>([...REQUESTS_KEY, id], (old) =>
        old ? { ...old, current_status: "rejected_by_hom" } : old
      );
      return { previous, id };
    },
    onError: (_err, { id }, context) => {
      if (context?.previous !== undefined) {
        qc.setQueryData([...REQUESTS_KEY, id], context.previous);
      }
    },
    onSettled: (_data, _err, { id }) => {
      invalidateRequestLists(qc);
      qc.invalidateQueries({ queryKey: [...REQUESTS_KEY, id] });
    },
  });
}

import { api } from "@/lib/api";
import type {
  ActivityItem,
  DepositRequest,
  DepositRequestDetail,
  InvoiceAdjustment,
  PaymentDetails,
  PaymentTranche,
  QueueKpis,
  RequestAuditEntry,
} from "@/types";

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface TranchePayload {
  amount: number;
  tentative_payment_date: string;
}

export interface CreateRequestPayload {
  supplier_id: string;
  customer_id: string;
  vertical_id: string;
  supplier_invoice_number?: string;
  sunshine_invoice_number?: string;
  currency: string;
  exchange_rate?: number;
  // Derived from tranches when they are supplied.
  deposit_amount?: number;
  deposit_percentage?: number;
  total_supplier_invoice_amount: number;
  estimated_etd?: string;
  payment_terms?: string;
  remarks?: string;
  override_flagged_supplier?: boolean;
  tranches?: TranchePayload[];
}

export type UpdateRequestPayload = Partial<CreateRequestPayload>;

const requestService = {
  list: async (params?: Record<string, string>): Promise<DepositRequest[]> => {
    // Fetch up to 1000 records for legacy callers (analytics, drill pages) that need all data.
    const { data } = await api.get<PaginatedResponse<DepositRequest>>("/requests", {
      params: { ...params, page: "1", page_size: "1000" },
    });
    return data.items;
  },

  listPaginated: async (
    page: number,
    pageSize: number,
    params?: Record<string, string | string[]>,
  ): Promise<PaginatedResponse<DepositRequest>> => {
    const sp = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (Array.isArray(v)) v.forEach((s) => sp.append(k, s));
        else sp.append(k, v);
      }
    }
    const { data } = await api.get<PaginatedResponse<DepositRequest>>(`/requests?${sp}`);
    return data;
  },

  pendingQueue: async (): Promise<DepositRequest[]> => {
    const { data } = await api.get<DepositRequest[]>("/requests/pending-payment-queue");
    return data;
  },

  // FY-to-date (April–March) KPI counts for the payment queue
  // (UAT Aug 2026, items 5/17/19).
  queueKpis: async (): Promise<QueueKpis> => {
    const { data } = await api.get<QueueKpis>("/requests/queue-kpis");
    return data;
  },

  get: async (id: string): Promise<DepositRequestDetail> => {
    const { data } = await api.get<DepositRequestDetail>(`/requests/${id}`);
    return data;
  },

  create: async (payload: CreateRequestPayload): Promise<DepositRequest> => {
    const { data } = await api.post<DepositRequest>("/requests", payload);
    return data;
  },

  // Pre-submit duplicate check — the server re-validates on create/update.
  checkInvoiceNumber: async (
    field: "sunshine_invoice_number" | "supplier_invoice_number",
    value: string,
  ): Promise<{ duplicate: boolean; request_number: string | null }> => {
    const { data } = await api.get<{ duplicate: boolean; request_number: string | null }>(
      `/requests/check-invoice?field=${field}&value=${encodeURIComponent(value)}`,
    );
    return data;
  },

  update: async (id: string, payload: UpdateRequestPayload): Promise<DepositRequest> => {
    const { data } = await api.patch<DepositRequest>(`/requests/${id}`, payload);
    return data;
  },

  hold: async (id: string, remarks?: string): Promise<void> => {
    await api.post(`/requests/${id}/hold`, { remarks });
  },

  resume: async (id: string, remarks?: string): Promise<void> => {
    await api.post(`/requests/${id}/resume`, { remarks });
  },

  cancel: async (id: string, remarks?: string): Promise<void> => {
    await api.post(`/requests/${id}/cancel`, { remarks });
  },

  reopen: async (id: string, remarks?: string): Promise<void> => {
    await api.post(`/requests/${id}/reopen`, { remarks });
  },

  getPayment: async (id: string): Promise<PaymentDetails | null> => {
    const { data } = await api.get<PaymentDetails | null>(`/requests/${id}/payment`);
    return data;
  },

  // savePayment / processPayment were removed with the request-level Payment
  // Details form (Aug 2026 follow-up) — details are captured per tranche; the
  // POST /payment and /payment/process endpoints remain API-only legacy.

  // Works on locked (processed) records — recording the final ship date is the
  // designed post-lock action that stops Cost of Fund accrual.
  saveShipDate: async (id: string, shipDate: string): Promise<PaymentDetails> => {
    const { data } = await api.post<PaymentDetails>(`/requests/${id}/payment/ship-date`, {
      ship_date: shipDate,
    });
    return data;
  },

  updateRemarks: async (id: string, remarks: string): Promise<void> => {
    await api.post(`/requests/${id}/remarks`, { remarks: remarks || null });
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/requests/${id}`);
  },

  homQueue: async (): Promise<DepositRequest[]> => {
    const { data } = await api.get<DepositRequest[]>("/requests/hom-queue");
    return data;
  },

  homApprove: async (id: string, remarks: string): Promise<void> => {
    await api.post(`/requests/${id}/hom-approve`, { remarks });
  },

  homReject: async (id: string, remarks: string): Promise<void> => {
    await api.post(`/requests/${id}/hom-reject`, { remarks });
  },

  // Accounts reject the whole request — terminal, reason mandatory
  // (UAT Aug 2026, items 12/17/18).
  rejectRequest: async (id: string, remarks: string): Promise<void> => {
    await api.post(`/requests/${id}/reject`, { remarks });
  },

  myActivity: async (limit = 50): Promise<ActivityItem[]> => {
    const { data } = await api.get<ActivityItem[]>(`/requests/my-activity?limit=${limit}`);
    return data;
  },

  myFieldVisibility: async (): Promise<Record<string, boolean>> => {
    const { data } = await api.get<Record<string, boolean>>("/requests/my-field-visibility");
    return data;
  },

  // ── Advance Payment Tranches ─────────────────────────────────────────────

  listTranches: async (id: string): Promise<PaymentTranche[]> => {
    const { data } = await api.get<PaymentTranche[]>(`/requests/${id}/tranches`);
    return data;
  },

  updateTranche: async (
    id: string,
    trancheId: string,
    payload: Partial<TranchePayload>,
  ): Promise<PaymentTranche> => {
    const { data } = await api.patch<PaymentTranche>(
      `/requests/${id}/tranches/${trancheId}`,
      payload,
    );
    return data;
  },

  // Merchandiser tranche management — only while the request is pending and
  // untouched by Accounts (server-enforced; `tranchesModifiable` mirrors it).
  addTranche: async (id: string, payload: TranchePayload): Promise<PaymentTranche> => {
    const { data } = await api.post<PaymentTranche>(`/requests/${id}/tranches`, payload);
    return data;
  },

  deleteTranche: async (id: string, trancheId: string): Promise<void> => {
    await api.delete(`/requests/${id}/tranches/${trancheId}`);
  },

  tranchesModifiable: async (
    id: string,
  ): Promise<{ modifiable: boolean; reason: string | null; can_add: boolean }> => {
    const { data } = await api.get<{
      modifiable: boolean;
      reason: string | null;
      can_add: boolean;
    }>(`/requests/${id}/tranches/modifiable`);
    return data;
  },

  // Accounts: per-tranche payment details + explicit mark-paid (Aug 2026).
  updateTranchePaymentDetails: async (
    id: string,
    trancheId: string,
    payload: {
      payment_date?: string;
      bank?: string;
      payment_reference_number?: string;
      accounts_remarks?: string;
    },
  ): Promise<PaymentTranche> => {
    const { data } = await api.patch<PaymentTranche>(
      `/requests/${id}/tranches/${trancheId}/payment-details`,
      payload,
    );
    return data;
  },

  payTranche: async (id: string, trancheId: string): Promise<PaymentTranche> => {
    const { data } = await api.post<PaymentTranche>(
      `/requests/${id}/tranches/${trancheId}/pay`,
    );
    return data;
  },

  rejectTranche: async (id: string, trancheId: string, reason: string): Promise<PaymentTranche> => {
    const { data } = await api.post<PaymentTranche>(
      `/requests/${id}/tranches/${trancheId}/reject`,
      { reason },
    );
    return data;
  },

  uploadTrancheTtCopy: async (
    id: string,
    trancheId: string,
    file: File,
  ): Promise<PaymentTranche> => {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<PaymentTranche>(
      `/requests/${id}/tranches/${trancheId}/tt-copy`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  },

  auditTrail: async (id: string): Promise<RequestAuditEntry[]> => {
    const { data } = await api.get<RequestAuditEntry[]>(`/requests/${id}/audit`);
    return data;
  },

  adjustments: async (id: string): Promise<InvoiceAdjustment[]> => {
    const { data } = await api.get<InvoiceAdjustment[]>(`/requests/${id}/adjustments`);
    return data;
  },
};

export default requestService;

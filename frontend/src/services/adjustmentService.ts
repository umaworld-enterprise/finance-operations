import { api } from "@/lib/api";
import type { InvoiceAdjustment, SupplierTrancheOptions } from "@/types";

export interface CreateAdjustmentPayload {
  source_tranche_id: string;
  destination_tranche_id: string;
  amount: number;
  reason?: string;
}

const adjustmentService = {
  list: async (limit = 100): Promise<InvoiceAdjustment[]> => {
    const { data } = await api.get<InvoiceAdjustment[]>(`/adjustments?limit=${limit}`);
    return data;
  },

  create: async (payload: CreateAdjustmentPayload): Promise<InvoiceAdjustment> => {
    const { data } = await api.post<InvoiceAdjustment>("/adjustments", payload);
    return data;
  },

  supplierOptions: async (supplierId: string): Promise<SupplierTrancheOptions> => {
    const { data } = await api.get<SupplierTrancheOptions>(
      `/adjustments/supplier/${supplierId}/options`,
    );
    return data;
  },

  // ── Accounts queue (merchandiser-raised adjustment requests) ─────────────

  pending: async (): Promise<InvoiceAdjustment[]> => {
    const { data } = await api.get<InvoiceAdjustment[]>("/adjustments/pending");
    return data;
  },

  approve: async (id: string, reason: string): Promise<InvoiceAdjustment> => {
    const { data } = await api.post<InvoiceAdjustment>(`/adjustments/${id}/approve`, { reason });
    return data;
  },

  reject: async (id: string, reason: string): Promise<InvoiceAdjustment> => {
    const { data } = await api.post<InvoiceAdjustment>(`/adjustments/${id}/reject`, { reason });
    return data;
  },
};

export default adjustmentService;

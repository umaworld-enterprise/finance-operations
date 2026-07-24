import { api } from "@/lib/api";
import type { AnalyticsSnapshot, AnalyticsSummary, NpaResponse } from "@/types";

export interface AnalyticsFilters {
  supplier_id?: string;
  customer_id?: string;
  vertical_id?: string;
  staff_id?: string;
  date_from?: string;
  date_to?: string;
}

function toParams(filters?: AnalyticsFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (!filters) return params;
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v;
  }
  return params;
}

export const analyticsService = {
  getSummary: async (filters?: AnalyticsFilters): Promise<AnalyticsSummary> => {
    const { data } = await api.get<AnalyticsSummary>("/analytics/summary", {
      params: toParams(filters),
    });
    return data;
  },

  getSnapshots: async (filters?: AnalyticsFilters): Promise<AnalyticsSnapshot[]> => {
    const { data } = await api.get<AnalyticsSnapshot[]>("/analytics/requests", {
      params: toParams(filters),
    });
    return data;
  },

  recalculate: async (): Promise<void> => {
    await api.post("/analytics/recalculate");
  },

  getNpa: async (): Promise<NpaResponse> => {
    const { data } = await api.get<NpaResponse>("/analytics/npa");
    return data;
  },
};

export default analyticsService;

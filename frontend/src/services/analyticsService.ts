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

// Weekly Deposit Tracker — unpaid deposits bucketed by ETD week (Aug 2026).
export interface WeeklyDepositRow {
  request_id: string;
  request_number: string;
  sunshine_invoice_number: string | null;
  supplier_name: string;
  tranche_label: string;
  currency: string;
  amount: number;
  tentative_payment_date: string | null;
  estimated_etd: string | null;
}

export interface WeeklyDepositGroup {
  week: string;
  week_start: string | null;
  rows: WeeklyDepositRow[];
  outstanding: Record<string, number>;
}

// All-shipments Analytical Snapshot row (Aug 2026).
export interface ShipmentRow {
  request_id: string;
  request_number: string;
  sunshine_invoice_number: string | null;
  supplier_name: string;
  currency: string | null;
  amount: number;
  estimated_etd: string | null;
  /** Server-computed: max(0, today − estimated_etd); null when no ETD. */
  days_delayed: number | null;
  current_status: string;
  /** Request creation date — drives the "Request date (new → old)" sort. */
  created_at: string | null;
  /** Payment date beside every paid amount (2 Sep 2026). */
  payment_date: string | null;
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

  getWeeklyDeposits: async (): Promise<WeeklyDepositGroup[]> => {
    const { data } = await api.get<WeeklyDepositGroup[]>("/analytics/weekly-deposits");
    return data;
  },

  getShipments: async (): Promise<ShipmentRow[]> => {
    const { data } = await api.get<ShipmentRow[]>("/analytics/shipments");
    return data;
  },
};

export default analyticsService;

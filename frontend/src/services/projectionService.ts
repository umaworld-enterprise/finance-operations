import { api } from "@/lib/api";

// Projections module (4 Sep 2026; reworked 7 Oct 2026): monthly per-vertical
// projections in USD / EUR / CNY, collected 25th→EOM for the NEXT month.
// Verticals are not assigned to anyone — ANY merchandiser may fill or
// overwrite ANY vertical, and a vertical still missing the current month's
// projection is LOCKED for request creation until someone files it.

export interface ProjectionStatusVertical {
  vertical_id: string;
  name: string;
  filled: boolean;
  amount_usd: number | null;
  amount_eur: number | null;
  amount_cny: number | null;
  /** Who last typed these figures — anyone may overwrite a colleague's. */
  last_updated_by: string | null;
  last_updated_at: string | null;
  /** Current month missing → no new requests for this vertical. */
  locked: boolean;
}

export interface ProjectionStatus {
  window_open: boolean;
  window_ends: string;
  target_year: number;
  target_month: number;
  verticals: ProjectionStatusVertical[];
  /** Verticals with no projection for the TARGET (next) month. */
  missing_target: string[];
  /** Verticals locked right now for request creation. */
  locked_verticals: string[];
}

export interface ProjectionSubmitItem {
  vertical_id: string;
  amount_usd: number;
  amount_eur: number;
  amount_cny: number;
}

export interface ProjectionDashboardRow {
  vertical_id: string;
  vertical: string;
  merchandiser: string | null;
  filled: boolean;
  proj_usd: number;
  proj_eur: number;
  proj_cny: number;
  actual_usd: number;
  actual_eur: number;
  actual_cny: number;
}

const projectionService = {
  status: async (): Promise<ProjectionStatus> => {
    const { data } = await api.get<ProjectionStatus>("/projections/status");
    return data;
  },

  submit: async (
    year: number,
    month: number,
    items: ProjectionSubmitItem[],
  ): Promise<{ saved: number }> => {
    const { data } = await api.post<{ saved: number }>("/projections", { year, month, items });
    return data;
  },

  dashboard: async (
    year: number,
    month: number,
  ): Promise<{ year: number; month: number; rows: ProjectionDashboardRow[] }> => {
    const { data } = await api.get("/projections/dashboard", { params: { year, month } });
    return data;
  },
};

export default projectionService;

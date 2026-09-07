import { api } from "@/lib/api";
import type { Vertical } from "@/types";

// Projections module (4 Sep 2026): monthly per-vertical projections in
// USD / EUR / CNY, collected 25th→EOM for the NEXT month; the dashboard
// compares them against the month's actual requested deposit amounts.

export interface ProjectionStatusVertical {
  vertical_id: string;
  name: string;
  filled: boolean;
  amount_usd: number | null;
  amount_eur: number | null;
  amount_cny: number | null;
}

export interface ProjectionStatus {
  has_verticals: boolean;
  window_open: boolean;
  window_ends: string;
  target_year: number;
  target_month: number;
  verticals: ProjectionStatusVertical[];
  missing_target: string[];
  blocked: boolean;
  block_message: string | null;
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

  // Bind verticals to ONE user (Super Admin) — the list becomes the user's
  // full assignment set; a vertical can belong to only one user.
  assignVerticals: async (userId: string, verticalIds: string[]): Promise<Vertical[]> => {
    const { data } = await api.put<Vertical[]>(
      `/masters/verticals/assignments/${userId}`,
      verticalIds,
    );
    return data;
  },
};

export default projectionService;

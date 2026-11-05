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

/** The per-vertical request lock (9 Oct 2026). Opt-in: off unless a Super
 * Admin arms it, so a missing projection never blocks request creation. */
export interface ProjectionLockSetting {
  lock_enabled: boolean;
}

/** Projection reminder (5 Nov 2026) — ADVISORY ONLY. Shown on the request
 * form when the chosen vertical still owes a projection; it never blocks. */
export interface ProjectionReminder {
  year: number;
  month: number;
  /** "October 2026" */
  period_label: string;
  /** "31 October 2026" */
  deadline_label: string;
  deadline: string;
  pending: { vertical_id: string; name: string }[];
}

/** One month of the confirmation form's trend. */
export interface ProjectionTrendRow {
  year: number;
  month: number;
  /** "Oct 2026" */
  label: string;
  filled: boolean;
  proposed_usd: number;
  proposed_eur: number;
  proposed_cny: number;
  actual_usd: number;
  actual_eur: number;
  actual_cny: number;
  /** Proposed − actual: positive = over-estimated, negative = under. */
  variance_usd: number;
  variance_eur: number;
  variance_cny: number;
}

export interface ProjectionTrend {
  vertical_id: string;
  vertical: string;
  year: number;
  month: number;
  /** "November 2026" */
  label: string;
  /** Newest month first, as the client's sheet is laid out. */
  rows: ProjectionTrendRow[];
  /** Average of the ACTUALS over the trend window — the suggested figure. */
  suggested_usd: number;
  suggested_eur: number;
  suggested_cny: number;
  confirmed: boolean;
  confirmed_usd: number | null;
  confirmed_eur: number | null;
  confirmed_cny: number | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  /** Editing stays open to the last day of the month being projected. */
  editable: boolean;
  editable_until: string;
}

const projectionService = {
  settings: async (): Promise<ProjectionLockSetting> => {
    const { data } = await api.get<ProjectionLockSetting>("/projections/settings");
    return data;
  },

  setLockEnabled: async (lockEnabled: boolean): Promise<ProjectionLockSetting> => {
    const { data } = await api.put<ProjectionLockSetting>("/projections/settings", {
      lock_enabled: lockEnabled,
    });
    return data;
  },

  reminders: async (): Promise<ProjectionReminder> => {
    const { data } = await api.get<ProjectionReminder>("/projections/reminders");
    return data;
  },

  trend: async (
    verticalId: string,
    year?: number,
    month?: number,
  ): Promise<ProjectionTrend> => {
    const { data } = await api.get<ProjectionTrend>("/projections/trend", {
      params: { vertical_id: verticalId, year, month },
    });
    return data;
  },

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

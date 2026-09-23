import { api } from "@/lib/api";
import type { NotificationList } from "@/types";

/** What landed in the Accounts queue while the user was away (23 Sep 2026).
 * `show` is the server's verdict: a real absence with new work in it. */
export interface AwaySummary {
  since: string | null;
  away_minutes: number;
  new_requests: number;
  show: boolean;
}

const notificationService = {
  list: async (page = 1, pageSize = 20): Promise<NotificationList> => {
    const { data } = await api.get<NotificationList>("/notifications", {
      params: { page: String(page), page_size: String(pageSize) },
    });
    return data;
  },

  markRead: async (ids: string[] | null): Promise<void> => {
    await api.post("/notifications/read", { ids });
  },

  // Presence heartbeat + "while you were away" summary (23 Sep 2026).
  heartbeat: async (): Promise<void> => {
    await api.post("/notifications/presence");
  },

  awaySummary: async (): Promise<AwaySummary> => {
    const { data } = await api.get<AwaySummary>("/notifications/away-summary");
    return data;
  },

  pushSubscribe: async (endpoint: string, p256dh: string, auth: string): Promise<void> => {
    await api.post("/notifications/push/subscribe", { endpoint, p256dh, auth });
  },

  pushUnsubscribe: async (endpoint: string): Promise<void> => {
    await api.post("/notifications/push/unsubscribe", { endpoint });
  },

  // uploadTtCopy (request-level) was removed with the Payment Details form
  // (Aug 2026 follow-up) — TT copies are uploaded per tranche.
};

export default notificationService;

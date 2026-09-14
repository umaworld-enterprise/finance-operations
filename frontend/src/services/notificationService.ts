import { api } from "@/lib/api";
import type { NotificationList } from "@/types";

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

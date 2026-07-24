import { api } from "@/lib/api";
import type { NotificationList, PaymentDetails } from "@/types";

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

  uploadTtCopy: async (requestId: string, file: File): Promise<PaymentDetails> => {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<PaymentDetails>(
      `/requests/${requestId}/payment/tt-copy`,
      form,
      // Override the client's JSON default so axios sets the multipart boundary.
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  },
};

export default notificationService;

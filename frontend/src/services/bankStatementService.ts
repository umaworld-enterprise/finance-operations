import { api } from "@/lib/api";
import type { BankStatement, BankStatementDetail } from "@/types";

// Banking module (Aug 2026) — super-admin only. Upload answers immediately
// with the statement in `processing`; extraction happens server-side via the
// configured AI vision provider.
const bankStatementService = {
  list: async (): Promise<BankStatement[]> => {
    const { data } = await api.get<BankStatement[]>("/bank/statements");
    return data;
  },

  get: async (id: string): Promise<BankStatementDetail> => {
    const { data } = await api.get<BankStatementDetail>(`/bank/statements/${id}`);
    return data;
  },

  upload: async (file: File): Promise<BankStatement> => {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<BankStatement>("/bank/statements", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  remove: async (id: string): Promise<void> => {
    await api.delete(`/bank/statements/${id}`);
  },
};

export default bankStatementService;

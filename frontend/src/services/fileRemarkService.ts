import { api } from "@/lib/api";
import type { FileRemark, FileRemarkCategory, SplitTarget } from "@/types";

export interface CreateFileRemarkPayload {
  deposit_request_id: string;
  category: FileRemarkCategory;
  old_file_number?: string;
  old_amount?: number;
  new_file_number?: string;
  new_amount?: number;
  split_targets?: SplitTarget[];
  remark?: string;
}

const fileRemarkService = {
  list: async (params?: {
    status?: "open" | "approved" | "rejected" | "resolved";
    request_id?: string;
  }): Promise<FileRemark[]> => {
    const { data } = await api.get<FileRemark[]>("/file-remarks", { params });
    return data;
  },

  create: async (payload: CreateFileRemarkPayload): Promise<FileRemark> => {
    const { data } = await api.post<FileRemark>("/file-remarks", payload);
    return data;
  },

  // Accounts decide: approve (processed, optional note) or reject
  // (mandatory reason) — UAT Aug 2026, item 14.
  decide: async (
    id: string,
    decision: "approved" | "rejected",
    responseNote?: string,
  ): Promise<FileRemark> => {
    const action = decision === "approved" ? "approve" : "reject";
    const { data } = await api.post<FileRemark>(`/file-remarks/${id}/${action}`, {
      response_note: responseNote || null,
    });
    return data;
  },
};

export default fileRemarkService;

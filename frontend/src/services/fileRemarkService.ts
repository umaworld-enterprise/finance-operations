import { api } from "@/lib/api";
import type { FileRemark, FileRemarkCategory } from "@/types";

export interface CreateFileRemarkPayload {
  deposit_request_id: string;
  category: FileRemarkCategory;
  old_file_number?: string;
  new_file_number?: string;
  remark: string;
}

const fileRemarkService = {
  list: async (params?: { status?: "open" | "resolved"; request_id?: string }): Promise<FileRemark[]> => {
    const { data } = await api.get<FileRemark[]>("/file-remarks", { params });
    return data;
  },

  create: async (payload: CreateFileRemarkPayload): Promise<FileRemark> => {
    const { data } = await api.post<FileRemark>("/file-remarks", payload);
    return data;
  },

  resolve: async (id: string, responseNote?: string): Promise<FileRemark> => {
    const { data } = await api.post<FileRemark>(`/file-remarks/${id}/resolve`, {
      response_note: responseNote || null,
    });
    return data;
  },
};

export default fileRemarkService;

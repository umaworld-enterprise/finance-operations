import { api } from "@/lib/api";
import type { FileRemark, FileRemarkCategory, SplitTarget } from "@/types";

export interface CreateFileRemarkPayload {
  deposit_request_id: string;
  category: FileRemarkCategory;
  /** The selected file within the request (19 Aug 2026 chain support) —
   * the root file or a live split-born / invoice-changed file. The server
   * validates it and derives the old amount from it. */
  file_number?: string;
  new_file_number?: string;
  split_targets?: SplitTarget[];
  /** Invoice Value Change (4 Sep 2026): the merchandiser's proposed amount. */
  proposed_amount?: number;
  remark?: string;
}

/** One selectable file in the New File Remark dropdown (19 Aug 2026):
 * the live files of every payment-completed request — root plus files born
 * from approved splits / invoice changes, any depth. */
export interface SelectableFile {
  deposit_request_id: string;
  request_number: string;
  file_number: string;
  amount: number;
  currency: string | null;
  is_root: boolean;
}

const fileRemarkService = {
  list: async (params?: {
    status?: "open" | "approved" | "rejected" | "resolved";
    request_id?: string;
  }): Promise<FileRemark[]> => {
    const { data } = await api.get<FileRemark[]>("/file-remarks", { params });
    return data;
  },

  selectableFiles: async (): Promise<SelectableFile[]> => {
    const { data } = await api.get<SelectableFile[]>("/file-remarks/selectable-files");
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

  // Invoice Value Change (4 Sep 2026): Accounts apply the final revised
  // amount on an APPROVED remark — the separate step after approval.
  applyRevisedAmount: async (id: string, revisedAmount: number): Promise<FileRemark> => {
    const { data } = await api.post<FileRemark>(`/file-remarks/${id}/revised-amount`, {
      revised_amount: revisedAmount,
    });
    return data;
  },
};

export default fileRemarkService;

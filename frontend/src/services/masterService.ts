import { api } from "@/lib/api";
import type { AppUser, Bank, Customer, DefaultedSupplier, PaymentTerm, Supplier, SupplierDefaultStatus, SupplierExposure, UserRole, Vertical } from "@/types";

export interface FlagSupplierPayload {
  supplier_id: string;
  outstanding_amount: number;
  currency: string;
  default_reason: string;
  flagged_date: string;
}

export interface CreateUserPayload {
  email: string;
  full_name: string;
  role: UserRole;
}

export interface UpdateUserPayload {
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
}

const masterService = {
  getPaymentTerms: async (): Promise<PaymentTerm[]> => {
    const { data } = await api.get<PaymentTerm[]>("/masters/payment-terms");
    return data;
  },

  getAllPaymentTerms: async (): Promise<PaymentTerm[]> => {
    const { data } = await api.get<PaymentTerm[]>("/masters/payment-terms/all");
    return data;
  },

  createPaymentTerm: async (label: string, sort_order = 0): Promise<PaymentTerm> => {
    const { data } = await api.post<PaymentTerm>("/masters/payment-terms", { label, sort_order });
    return data;
  },

  updatePaymentTerm: async (id: string, payload: { label?: string; is_active?: boolean; sort_order?: number }): Promise<PaymentTerm> => {
    const { data } = await api.patch<PaymentTerm>(`/masters/payment-terms/${id}`, payload);
    return data;
  },

  deletePaymentTerm: async (id: string): Promise<void> => {
    await api.delete(`/masters/payment-terms/${id}`);
  },

  getVerticals: async (): Promise<Vertical[]> => {
    const { data } = await api.get<Vertical[]>("/masters/verticals");
    return data;
  },

  getCustomers: async (): Promise<Customer[]> => {
    const { data } = await api.get<Customer[]>("/masters/customers");
    return data;
  },

  getSuppliers: async (): Promise<Supplier[]> => {
    const { data } = await api.get<Supplier[]>("/masters/suppliers");
    return data;
  },

  // ── Masters admin page (19 Aug 2026): active + inactive lists, create,
  //    update — suppliers, customers and verticals. ─────────────────────────

  getAllSuppliers: async (): Promise<Supplier[]> => {
    const { data } = await api.get<Supplier[]>("/masters/suppliers/all");
    return data;
  },

  createSupplier: async (payload: {
    supplier_code: string;
    name: string;
    country?: string;
  }): Promise<Supplier> => {
    const { data } = await api.post<Supplier>("/masters/suppliers", payload);
    return data;
  },

  updateSupplier: async (
    id: string,
    payload: { name?: string; country?: string; is_active?: boolean },
  ): Promise<Supplier> => {
    const { data } = await api.patch<Supplier>(`/masters/suppliers/${id}`, payload);
    return data;
  },

  getAllCustomers: async (): Promise<Customer[]> => {
    const { data } = await api.get<Customer[]>("/masters/customers/all");
    return data;
  },

  createCustomer: async (name: string): Promise<Customer> => {
    const { data } = await api.post<Customer>("/masters/customers", { name });
    return data;
  },

  updateCustomer: async (
    id: string,
    payload: { name?: string; is_active?: boolean },
  ): Promise<Customer> => {
    const { data } = await api.patch<Customer>(`/masters/customers/${id}`, payload);
    return data;
  },

  getAllVerticals: async (): Promise<Vertical[]> => {
    const { data } = await api.get<Vertical[]>("/masters/verticals/all");
    return data;
  },

  createVertical: async (name: string): Promise<Vertical> => {
    const { data } = await api.post<Vertical>("/masters/verticals", { name });
    return data;
  },

  updateVertical: async (
    id: string,
    payload: { name?: string; is_active?: boolean },
  ): Promise<Vertical> => {
    const { data } = await api.patch<Vertical>(`/masters/verticals/${id}`, payload);
    return data;
  },

  // ── Bank master (Aug 2026) ────────────────────────────────────────────────

  getBanks: async (): Promise<Bank[]> => {
    const { data } = await api.get<Bank[]>("/masters/banks");
    return data;
  },

  getAllBanks: async (): Promise<Bank[]> => {
    const { data } = await api.get<Bank[]>("/masters/banks/all");
    return data;
  },

  createBank: async (name: string, sortOrder = 0): Promise<Bank> => {
    const { data } = await api.post<Bank>("/masters/banks", { name, sort_order: sortOrder });
    return data;
  },

  updateBank: async (
    id: string,
    payload: { name?: string; is_active?: boolean; sort_order?: number },
  ): Promise<Bank> => {
    const { data } = await api.patch<Bank>(`/masters/banks/${id}`, payload);
    return data;
  },

  deleteBank: async (id: string): Promise<void> => {
    await api.delete(`/masters/banks/${id}`);
  },

  checkSupplierDefault: async (supplierId: string): Promise<SupplierDefaultStatus> => {
    const { data } = await api.get<SupplierDefaultStatus>(
      `/masters/suppliers/${supplierId}/default-status`
    );
    return data;
  },

  getDefaultedSuppliers: async (): Promise<DefaultedSupplier[]> => {
    const { data } = await api.get<DefaultedSupplier[]>("/masters/suppliers/defaulted");
    return data;
  },

  // Full default history (active + resolved flags) for one supplier — shown
  // on request detail pages so approvers see the track record (Aug 2026).
  getSupplierDefaultHistory: async (supplierId: string): Promise<DefaultedSupplier[]> => {
    const { data } = await api.get<DefaultedSupplier[]>(
      `/masters/suppliers/${supplierId}/default-history`,
    );
    return data;
  },

  // Whole live exposure — open requests split by graced-ETD passed vs not
  // yet passed (UAT Aug 2026, item 2).
  getSupplierExposure: async (supplierId: string): Promise<SupplierExposure> => {
    const { data } = await api.get<SupplierExposure>(
      `/masters/suppliers/${supplierId}/exposure`,
    );
    return data;
  },

  flagSupplier: async (payload: FlagSupplierPayload): Promise<void> => {
    await api.post("/masters/suppliers/defaulted", payload);
  },

  resolveDefaultFlag: async (flagId: string): Promise<void> => {
    await api.post(`/masters/suppliers/defaulted/${flagId}/resolve`);
  },

  getUsers: async (): Promise<AppUser[]> => {
    const { data } = await api.get<AppUser[]>("/masters/users");
    return data;
  },

  createUser: async (payload: CreateUserPayload): Promise<AppUser> => {
    const { data } = await api.post<AppUser>("/masters/users", payload);
    return data;
  },

  updateUser: async (id: string, payload: UpdateUserPayload): Promise<AppUser> => {
    const { data } = await api.patch<AppUser>(`/masters/users/${id}`, payload);
    return data;
  },
};

export default masterService;

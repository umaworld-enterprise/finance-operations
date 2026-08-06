// ── Enums ─────────────────────────────────────────────────────────────────────

export type UserRole =
  | "super_admin"
  | "finance_admin"
  | "accounts_team"
  | "merchandiser"
  | "head_of_merchandiser";

export type RequestStatus =
  | "pending_payment"
  | "hold_by_merchandiser"
  | "hold_by_accounts"
  | "payment_processed"
  | "cancelled_by_merchandiser"
  | "cancelled_by_accounts"
  | "reopened"
  | "pending_hom_approval"
  | "rejected_by_hom";

export type CurrencyCode =
  | "USD" | "EUR" | "GBP" | "AED" | "INR" | "CNY" | "JPY" | "SGD" | "OTHER";

export type SubmissionSource = "google_form" | "google_sheet_sync" | "in_app";

// ── Master data ────────────────────────────────────────────────────────────────

export interface PaymentTerm {
  id: string;
  label: string;
  is_active: boolean;
  sort_order: number;
}

export interface Vertical {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
}

export interface Customer {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
}

export interface Supplier {
  id: string;
  supplier_code: string;
  name: string;
  country: string | null;
  is_active: boolean;
  fixed_deposit_amount: number | null;
}

export interface DefaultedSupplier {
  id: string;
  supplier_id: string;
  supplier_name: string;
  outstanding_amount: number;
  currency: CurrencyCode;
  default_reason: string;
  flagged_date: string;
  is_active: boolean;
  resolved_date: string | null;
}

// Bank master (Aug 2026) — names only; the tranche form composes the stored
// value as "{name} ({currency})" from the request's currency.
export interface Bank {
  id: string;
  name: string;
  is_active: boolean;
  sort_order: number;
}

export interface SupplierDefaultStatus {
  supplier_id?: string;
  is_defaulted: boolean;
  outstanding_amount: number | null;
  currency: CurrencyCode | null;
  default_reason: string | null;
}

export interface AppUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  onboarding_completed: boolean;
  secondary_email: string | null;
  department: string | null;
  font_size?: FontSize;
}

export type FontSize = "default" | "large" | "xlarge";

// ── Advance Payment Tranches ───────────────────────────────────────────────────

export type TrancheStatus = "unpaid" | "paid" | "rejected";

export interface PaymentTranche {
  id: string;
  deposit_request_id: string;
  tranche_number: number;
  label: string;
  amount: number;
  tentative_payment_date: string | null;
  /** amount / total supplier proforma invoice amount — system-calculated, read-only. */
  percentage_of_invoice: number | null;
  status: TrancheStatus;
  paid_at: string | null;
  paid_by: string | null;
  tt_copy_url: string | null;
  tt_copy_file_id: string | null;
  tt_copy_filename: string | null;
  /** Per-tranche payment details — payment date, bank and accounts remarks
   * are required before the tranche can be marked paid; reference number is
   * optional. */
  payment_date: string | null;
  bank: string | null;
  payment_reference_number: string | null;
  accounts_remarks: string | null;
  /** Set when Accounts rejected the tranche (Aug 2026) — the tranche stays
   * visible as a dead record and its amount stops counting. */
  rejection_reason: string | null;
  rejected_at: string | null;
  is_legacy: boolean;
  created_at: string;
  updated_at: string;
  adjusted_out_total: number | null;
  available_paid_balance: number | null;
  adjusted_in_total: number | null;
  request_number: string | null;
  request_currency: string | null;
  supplier_invoice_number: string | null;
  sunshine_invoice_number: string | null;
}

export type AdjustmentStatus = "completed" | "pending_approval" | "rejected";

export interface InvoiceAdjustment {
  id: string;
  source_tranche_id: string;
  destination_tranche_id: string;
  amount: number;
  reason: string | null;
  status: AdjustmentStatus;
  performed_by: string;
  created_at: string;
  performed_by_name: string | null;
  source_request_id: string | null;
  source_request_number: string | null;
  source_tranche_label: string | null;
  destination_request_id: string | null;
  destination_request_number: string | null;
  destination_tranche_label: string | null;
  supplier_name: string | null;
}

// File Remarks module (CIO batch 2, Aug 2026; reworked 4 Aug) — tracked
// merchandiser → Accounts communication on a payment-completed file;
// bypasses Adjust Invoices for now.
export type FileRemarkCategory = "invoice_split" | "invoice_amount_change";
export type FileRemarkStatus = "open" | "resolved";

export interface SplitTarget {
  file_number: string;
  amount: number;
}

export interface FileRemark {
  id: string;
  deposit_request_id: string;
  category: FileRemarkCategory;
  old_file_number: string | null;
  old_amount: number | null;
  new_file_number: string | null;
  new_amount: number | null;
  split_targets: SplitTarget[] | null;
  remark: string | null;
  status: FileRemarkStatus;
  created_by: string;
  created_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
  response_note: string | null;
  request_number: string | null;
  supplier_name: string | null;
  created_by_name: string | null;
  resolved_by_name: string | null;
}

export interface SupplierTrancheOptions {
  paid_sources: PaymentTranche[];
  unpaid_destinations: PaymentTranche[];
}

export interface RequestAuditEntry {
  id: string;
  entity_name: string;
  entity_id: string;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  action: string;
  changed_by_name: string | null;
  changed_by_email: string | null;
  changed_at: string;
}

// ── Deposit Request ────────────────────────────────────────────────────────────

export interface DepositRequest {
  id: string;
  request_number: string;
  supplier: Supplier;
  customer: Customer;
  vertical: Vertical | null;
  supplier_invoice_number: string | null;
  sunshine_invoice_number: string | null;
  currency: CurrencyCode | null;
  exchange_rate: number | null;
  deposit_amount: number;
  deposit_percentage: number | null;
  total_supplier_invoice_amount: number;
  estimated_etd: string | null;
  payment_terms: string | null;
  remarks: string | null;
  submission_source: SubmissionSource;
  current_status: RequestStatus;
  is_locked: boolean;
  created_by: string | null;
  creator: AppUser | null;
  created_at: string;
  updated_at: string;
  tranches: PaymentTranche[];
}

export interface DepositRequestDetail extends DepositRequest {
  status_history: StatusHistory[];
  submitter_email: string | null;
  analytics_snapshot: AnalyticsSnapshot | null;
}

export interface StatusHistory {
  id: string;
  old_status: RequestStatus | null;
  new_status: RequestStatus;
  remarks: string | null;
  changed_by: string | null;
  changed_at: string;
}

export interface ActivityItem {
  id: string;
  request_id: string;
  request_number: string;
  supplier_name: string;
  old_status: RequestStatus | null;
  new_status: RequestStatus;
  remarks: string | null;
  changed_at: string;
}

// ── Payment ────────────────────────────────────────────────────────────────────

export interface PaymentDetails {
  id: string;
  deposit_request_id: string;
  payment_date: string | null;
  bank: string | null;
  payment_reference_number: string | null;
  payment_status: string | null;
  ship_date: string | null;
  actual_etd: string | null;
  accounts_remarks: string | null;
  tt_copy_url: string | null;
  tt_copy_file_id: string | null;
  tt_copy_filename: string | null;
  updated_by: string | null;
  updated_at: string;
}

// ── Notifications ──────────────────────────────────────────────────────────────

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  url: string | null;
  attachment_url: string | null;
  deposit_request_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationList {
  items: AppNotification[];
  total: number;
  unread_count: number;
}

// ── Analytics ──────────────────────────────────────────────────────────────────

export interface AnalyticsSummary {
  total_requests: number;
  pending_payment_count: number;
  payment_processed_count: number;
  total_deposit_exposure: number;
  overdue_shipments: number;
  total_cost_of_fund: number;
  avg_payment_to_ship_days: number | null;
}

export interface AnalyticsSnapshot {
  deposit_request_id: string;
  request_number: string | null;
  current_status: RequestStatus | null;
  // Currency of the underlying request — cost_of_fund_amount is denominated in it.
  currency: string | null;
  grace_etd: string | null;
  etd_grace_overdue_days: number | null;
  payment_to_ship_days: number | null;
  payment_to_request_days: number | null;
  actual_etd_overdue_days: number | null;
  cost_of_fund_applicable: boolean | null;
  cost_of_fund_amount: number | null;
  default_status: string | null;
  calculated_at: string;
}

// ── NPA (Non-Performing Assets) ────────────────────────────────────────────────

export interface FlaggedSupplierNpa {
  supplier_id: string;
  supplier_name: string;
  flagged_date: string | null;
  default_reason: string | null;
  is_auto_flagged: boolean;
  is_formally_flagged: boolean;
  overdue_request_count: number;
  max_overdue_days: number;
}

export interface MerchandiserNpa {
  merchandiser_id: string;
  name: string;
  email: string;
  total_requests: number;
  overdue_count: number;
  avg_overdue_days: number | null;
}

export interface NpaResponse {
  flagged_suppliers: FlaggedSupplierNpa[];
  merchandiser_performance: MerchandiserNpa[];
}

// ── API response wrappers ──────────────────────────────────────────────────────

export interface MessageResponse {
  message: string;
}

export interface ApiError {
  error_code: string;
  message: string;
  detail: string | null;
}

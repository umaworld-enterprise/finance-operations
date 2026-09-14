// UI feature flags for modules hidden pending business decisions.

// Adjust Invoices is hidden from the UI as of the Aug 2026 UAT change note
// (item 15) until further discussion. The backend module and all frontend
// code stay intact — flip this to true to restore the nav entry's page and
// the adjustment panels on request detail views.
export const ADJUST_INVOICES_ENABLED = false;

# UAT Change Note — August 2026 (19 points)

Received 8 Aug 2026 from the UAT team. Nineteen numbered points, implemented
in eight phases. This file records what was actually built, phase by phase —
same living-doc convention as `docs/change-note-aug2026/IMPLEMENTED.md`.

## Decisions taken (with the client, 8 Aug)

- **Points 12/17/18 — "rejected by accounts"**: a real request-level
  `REJECTED_BY_ACCOUNTS` terminal status will be added (Phase 2), with a
  Reject Request action for Accounts. Tranche-level rejection stays for
  partial rework.
- **Point 1 — Bank Ledger report column N**: Deposit Amount.
- **Point 13 — 0–10 / >10 day split**: bucket by the earliest UNPAID
  tranche's tentative payment date; requests with no tentative date go in
  the > 10 days table.
- **Point 5 — FY-to-date KPIs**: all KPIs count requests **created** between
  1 April and today (financial year April–March).

## Phase plan

| Phase | Points | Summary |
|---|---|---|
| 1 | 9, 11, 15, 16 | Global UI sweeps: DD/MM/YYYY, arithmetic tranche numbers, hide Adjust Invoices, sidebar order |
| 2 | 12, 17 (validation), 18 | Request-level Rejected-by-Accounts status + workflow (migration 0028) |
| 3 | 5, 8, 13, 17 (KPI), 19 | Payment queue restructure: FY KPIs, new columns, 0–10/>10 split, Rejected & Cancelled tabs |
| 4 | 6, 7, 10 | Hold/cancel correctness: holder name, grey/lock on merch hold, auto-navigate back to queue |
| 5 | 2, 3 | HOM detail parity + supplier exposure (graced ETD passed / not yet passed) |
| 6 | 14 | File Remarks: Accounts summary view with Approve/Reject |
| 7 | 1 | Bank Ledger report |
| 8 | 4 | Auto-refresh (polling) |

---

## Phase 1 — Global UI sweeps · IMPLEMENTED (8 Aug 2026)

### Item 9 — DD/MM/YYYY across the entire PWA
- `frontend/src/lib/utils.ts` — `formatDate()` now renders `DD/MM/YYYY`
  (was `07 Aug 2026` style). Every list/detail/report page formats dates
  through this one function, so the change applies app-wide.
- New `formatDateTime()` helper (`DD/MM/YYYY, HH:MM`) for full timestamps;
  the audit-log detail drawer (`admin/audit/page.tsx`) now uses it instead
  of a locale-dependent `toLocaleString()`.
- Deliberately unchanged: `reports/page.tsx` `isoDate()` (YYYY-MM-DD — an
  API query-param value, not a display), number formatting via
  `toLocaleString`, and the raw `date` objects written into Excel/CSV report
  exports (spreadsheet apps render those in the viewer's locale). Backend
  user-facing date strings (weekly tracker labels) were already DD/MM/YYYY.

### Item 11 — Arithmetic tranche numbers (1, 2, 3) instead of Roman
- `backend/app/models/tranche.py` — `tranche_label()` now returns
  `"Deposit - Tranche 1"` etc. Single source: API responses, notifications,
  audit wording and adjustment pickers all inherit the change.
- `frontend/src/components/forms/NewRequestForm.tsx` — local `roman()`
  helper deleted; the request form labels tranches `Deposit - Tranche 1/2/…`
  and the fixed-deposit prefill notice says "Tranche 1".
- Tests updated: `test_tranche_schemas.py` (label assertions),
  `test_tranche_service.py`, `test_request_create_with_tranches.py`.
- Stored data is unaffected — labels are always derived from
  `tranche_number` at render time, never persisted.

### Item 15 — Adjust Invoices hidden from UI
- New flag `ADJUST_INVOICES_ENABLED = false` in
  `frontend/src/lib/features.ts` — flip to `true` to restore everything.
- Sidebar entry removed; the `/adjust-invoices` route now renders an
  "unavailable" notice (deep links/bookmarks don't 404); the Invoice
  Adjustments panels on the accounts and merchandiser request detail pages
  are suppressed (and their query is not even fetched).
- Backend module fully intact — endpoints, service, tests all still live.

### Item 16 — Left-panel chronology
- `frontend/src/components/layout/Sidebar.tsx` — nav order is now, for every
  role: *own dashboard(s) → File Remarks → Analytics → Reports → Settings*.
  Merchandiser sees exactly the requested order: My Requests, File Remarks,
  Analytics, Reports, Settings.

### Verification
- `pytest tests/unit -q` — 239 passed.
- `npx tsc --noEmit` — clean.
- No migration needed (head stays 0027).

---

## Phase 2 — Rejected by Accounts (items 12, 17-validation, 18) · IMPLEMENTED (8 Aug 2026)

### Migration 0028 (`0028_rejected_by_accounts.py`)
- `ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'rejected_by_accounts'`
  and `ALTER TYPE accounts_action_type ADD VALUE IF NOT EXISTS 'reject'`
  (outside the transaction — COMMIT first, pattern from 0013).
- `enforce_status_transition()` rebuilt with two new transitions:
  `pending_payment → rejected_by_accounts` and
  `hold_by_accounts → rejected_by_accounts`. Downgrade restores the 0012
  body (enum labels stay — Postgres can't drop them — but become unusable).
- All three status-rule locations changed together: `enums.py`,
  `status_transitions.py` (Accounts/Super only), and the trigger.

### Backend
- **API:** `POST /requests/{id}/reject` — Accounts/Super only, body reuses
  `HomDecisionRequest` so the reason is mandatory (`min_length=1`). Audited
  via `transition_status` (StatusHistory + `AccountsAction(reject)` row +
  audit log), then notifies in the background.
- **Item 17 (validation):** `rejected_by_accounts` added to
  `_DUPLICATE_EXEMPT_STATUSES` — the rejected file's sunshine/proforma
  invoice numbers immediately become reusable on a new request.
- **Item 18 (edit lock):** merchandiser writes are blocked on all four
  terminal statuses (`_MERCHANDISER_EDIT_BLOCKED_STATUSES` = the exempt
  set): generic PATCH (`update`), remarks (`update_remarks`), and every
  tranche operation (`rejected_by_accounts` joined `_TERMINAL_STATUSES`
  in `tranche_service`, which also blocks accounts-side payment writes on
  the closed request). `GET /tranches/modifiable` returns
  `modifiable=false, can_add=false` automatically since the status is no
  longer pending.
- **Item 12 (notification):** `notify_request_rejected_by_accounts` —
  bell + push with the reason to the raising merchandiser AND every active
  HoM; per-audience deep links (`/merchandiser/{id}` vs `/hom/{id}`).
  Type `request_rejected`; matrix updated.

### Frontend
- `types` — `"rejected_by_accounts"` added to `RequestStatus`; all
  exhaustive `Record<RequestStatus, …>` maps extended (StatusBadge labels
  "Rejected" / "Rejected by Accounts", strikethrough treatment, X icon,
  red left-border on merchandiser lists).
- Accounts detail page — destructive **Reject Request** button (visible on
  `pending_payment` / `hold_by_accounts`, hidden for finance) opening the
  shared mandatory-reason DecisionDialog; on success it toasts and routes
  straight back to `/accounts` (early piece of item 10).
- `useRejectRequest` mutation (optimistic status flip + list invalidation),
  `requestService.rejectRequest`.
- Merchandiser detail page — on any terminal status the Remarks card
  becomes read-only ("This request is closed"), Save button hidden;
  hold/cancel buttons already vanish by status; tranche editing is blocked
  by the backend `modifiable` flags.

### Tests (`test_request_rejection_by_accounts.py`, 6 new — 245 total)
- Transition rules (Accounts/Super from pending & hold; merchandiser never;
  terminal — nothing leads out).
- Service flow writes StatusHistory with the reason + `AccountsAction(reject)`.
- Invoice numbers freed for reuse after rejection (both fields).
- Full merchandiser edit-lock (PATCH, remarks, add-tranche) after rejection.
- Hold/resume/reopen impossible after rejection.
- Notification fan-out: merchandiser + every HoM, reason in body,
  per-audience URLs.

### Verification
- `pytest tests/unit -q` — 245 passed.
- `npx tsc --noEmit` — clean.
- `alembic heads` — single head `0028`. Deploy: run `alembic upgrade head`.

---

## Phase 3 — Payment queue restructure (items 5, 8, 13, 17-KPI, 19) · IMPLEMENTED (8 Aug 2026)

### Item 5 — FY-to-date KPIs (April–March)
- New endpoint `GET /requests/queue-kpis` (Accounts/Super) —
  `DepositRequestService.get_queue_kpis()`: one grouped count query over
  requests **created** since 1 April of the current FY, returning
  `pending_payment / awaiting_hom / on_hold / processed / rejected /
  cancelled / total` plus `fy_start` and a display `fy_label`
  (e.g. "FY 2026–27").
- Replaces the previous four all-time client-side count queries. Cards show
  "FY 2026–27 to date" as subtext and refresh on the same poll/invalidation
  cycle as the queue (`useQueueKpis`, invalidated by every request mutation).

### Items 17 & 19 — Rejected and Cancelled heads
- Two new KPI cards: **Rejected** (`rejected_by_accounts` +
  `rejected_by_hom`) and **Cancelled** (`cancelled_by_merchandiser` +
  `cancelled_by_accounts`) — six cards total.
- Two new tabs on the queue ("Rejected", "Cancelled"), each a paginated,
  searchable list with status badges. Pending only ever contains
  `pending_payment` requests (it always did server-side — the queue query
  filters on that status), so rejected/cancelled never mix into it.

### Item 13 — Pending bifurcation by tentative payment date
- The Pending tab now renders two tables: **"Tentative Payment in 0–10
  Days"** and **"Tentative Payment in > 10 Days"**.
- Bucketing key: the earliest `tentative_payment_date` among the request's
  UNPAID tranches (client-side — the queue response already carries full
  tranches). Requests with no tentative date fall in the > 10 days table,
  per the decision recorded above.
- A "Tentative Payment" column shows the bucketing date on each row.

### Item 8 — New pending-table columns
- **Vertical/Category** and **Merchandiser** columns added (desktop table
  and mobile cards). No backend change — `DepositRequestResponse` already
  serialises `vertical` and `creator`, and the queue eagerly loads both.

### Refactor
- `HoldTable` generalised to `StatusTable` (title/subtitle/empty-state
  props) — serves the On Hold, Rejected and Cancelled tabs.

### Tests (`test_queue_kpis.py`, 2 new — 247 total)
- All six buckets count correctly by status within the FY window.
- Requests created before 1 April are excluded from every bucket.

### Verification
- `pytest tests/unit -q` — 247 passed.
- `npx tsc --noEmit` — clean.
- No new migration (head stays 0028).

---

## Phase 4 — Hold/cancel correctness (items 6, 7, 10) · IMPLEMENTED (8 Aug 2026)

### Item 6 — WHO held/cancelled, by name
- Root cause: the badge's full labels were written from the merchandiser's
  perspective — `"On Hold (by you)"` rendered for EVERY viewer, so Accounts
  saw merchandiser holds attributed to themselves. Labels are now
  viewer-neutral ("On Hold (by Merchandiser)" / "(by Accounts)").
- The actual person: new `DepositRequestService.get_last_status_actors()`
  (one batch query — latest status-history row per request joined to users)
  populates `last_status_change_by` on `DepositRequestResponse`, filled by
  the list endpoint (all queue tabs) and the detail endpoint.
- UI: a **By** column on the On Hold / Rejected / Cancelled tabs, and
  "by {name}" beside the status badge on the accounts detail header.

### Item 7 — Merchandiser hold/cancel freezes Accounts completely
- Backend (the real enforcement): new
  `TrancheService._assert_not_held_by_merchandiser()` guard on every
  accounts write — `update_payment_details`, `attach_tt_copy`,
  `reject_tranche` and `pay_tranche` (whose status check now fires BEFORE
  the readiness gate, so a held request fails with "held", not a
  misleading missing-TT message). `attach_tt_copy` also gained the
  terminal-status check it previously lacked. Merchandiser-cancelled
  requests were already frozen via `_TERMINAL_STATUSES`.
- Frontend: merchandiser-held/cancelled rows render greyed and
  non-clickable ("Locked by merchandiser", no View button,
  `pointer-events-none`) on the On Hold / Cancelled / All tabs. A
  deep-linked detail page shows an information banner and renders the
  tranche panel read-only; the Actions card is already empty for those
  statuses. Routing was already correct: held/cancelled requests never
  enter the HoM queue (pending_hom_approval only) or the pending queue
  (pending_payment only) — they exist for notification purposes only,
  and hold/cancel notifications were wired in the Aug 2026 batch.

### Item 10 — Automatic return to the queue
- Paying the FINAL tranche (request completes and locks) → toast + route
  back to `/accounts` (new `onRequestCompleted` callback on `TrancheList`,
  computed from "this was the last unpaid live tranche").
- Cancel Request → back to `/accounts`. Reject Request already navigated
  (Phase 2). Hold/Resume stay on the page (the record remains actionable).

### Tests (`test_merchandiser_hold_freeze.py`, 5 new — 252 total)
- Payment details, TT attach, tranche reject and tranche pay all refuse on
  a merchandiser-held request (pay with the "held" message specifically).
- TT attach refuses on cancelled requests (the previously missing guard).
- `get_last_status_actors` names the holder and tracks the latest actor.

### Verification
- `pytest tests/unit -q` — 252 passed.
- `npx tsc --noEmit` — clean.
- No new migration (head stays 0028).

---

## Phase 5 — HOM parity + supplier exposure (items 2, 3) · IMPLEMENTED (8 Aug 2026)

### Item 3 — HOM sees the same particulars as Accounts
The HoM request view (`hom/[id]/page.tsx`) gained everything it lacked
relative to the accounts view:
- **Advance Payment Tranches** panel — read-only `TrancheList` (amounts,
  tentative dates, per-tranche payment progress/TT links), the exact data
  Accounts work from.
- **Cost of Fund** added to the Analytics card (behind the same
  `cost_of_fund` field-visibility key as accounts).
- **Ship Date** and **Payment Last Updated** in the details grid (when a
  payment row exists).
- **Request Audit Trail** panel (endpoint already permitted HoM).
All view-only — HoM decisions remain approve/reject.

### Item 2 — Supplier Default History now shows the WHOLE exposure
- New endpoint `GET /masters/suppliers/{id}/exposure` — every open request
  for the supplier (not cancelled/rejected, **goods not yet shipped** — a
  recorded ship date ends the exposure), joined to its analytics snapshot,
  split into:
  - **Graced ETD passed** — grace expired, goods not shipped (defaulting
    behaviour, with overdue days), and
  - **Graced ETD not yet passed** — open commitments inside the grace
    window (the previously-missing half).
  Plus per-currency deposit totals. Requests without a snapshot count as
  pending (still exposure).
- The `SupplierDefaultHistory` panel renders a "Live Exposure" section with
  both tables and the total; the panel now appears whenever the supplier
  has flags **or** live exposure (previously flags only). Because HoM
  approval, the Accounts detail page and the merchandiser detail all mount
  the same component, the payment queue view changed simultaneously —
  exactly as the change note asked.

### Tests (`test_supplier_exposure.py`, 2 new — 254 total)
- Bucketing (passed vs pending vs no-snapshot), exclusions (cancelled,
  rejected-by-accounts, shipped, other suppliers) and per-currency totals.
- Clean supplier returns an empty exposure.

### Verification
- `pytest tests/unit -q` — 254 passed.
- `npx tsc --noEmit` — clean.
- No new migration (head stays 0028).

---

## Phase 6 — File Remarks: Accounts decide with Approve/Reject (item 14) · IMPLEMENTED (8 Aug 2026)

### Migration 0029 (`0029_file_remark_decisions.py`)
- Widens `ck_file_remarks_status` to
  `('open', 'approved', 'rejected', 'resolved')`. Existing `resolved` rows
  stay valid (shown as a legacy "Resolved"). A separate migration — NOT an
  amendment of 0025 (7 Aug lesson). Downgrade maps decisions back to
  `resolved` and restores the tight CHECK.

### Backend
- `FileRemarkStatus` gains `APPROVED` / `REJECTED`; model CHECK updated.
- `FileRemarkService.resolve()` → **`decide(remark_id, decision, …)`**:
  approve with an optional note, reject with a **mandatory reason**
  (`ValidationError` otherwise); double decisions conflict; audit rows say
  `approved`/`rejected` and land on both the remark and the request trail.
- API: `POST /file-remarks/{id}/approve` and `/{id}/reject` (shared
  `FileRemarkDecide` body) replace `/{id}/resolve`. The list endpoint's
  status filter accepts all four values.
- `notify_file_remark_resolved` → **`notify_file_remark_decided`** — the
  raiser's bell + push says "approved and processed" or "rejected" and
  carries the note/reason. Stored notification type value stays
  `file_remark_resolved` for continuity; matrix updated.

### Frontend (`file-remarks/page.tsx`)
- **Accounts no longer see the merchandiser form** — their view is the
  decision queue: the summary of each requested change (category, file
  numbers, amounts, split rows, raiser) with two buttons per row:
  **Processed / Approve** (optional note) and **Reject** (dialog blocks
  until a reason is typed). The raise form remains for merchandisers (and
  super admin, for support).
- Status pills: Open (amber) / Approved (green) / Rejected (red) /
  Resolved (legacy, green) in the shared history table.

### Tests (`test_file_remarks.py` reworked, 11 in file — 255 total)
- Approve flow (optional note), reject requires a reason, invalid decision
  value refused, double-decision conflict, non-decider roles blocked.
- Notification test covers both outcomes: raiser gets "approved and
  processed" / "rejected" with the note and reason.

### Verification
- `pytest tests/unit -q` — 255 passed.
- `npx tsc --noEmit` — clean.
- `alembic heads` — single head `0029`. Deploy: run `alembic upgrade head`.

---

## Phase 7 — Bank Ledger report (item 1) · IMPLEMENTED (8 Aug 2026)

- New endpoint `GET /reports/bank-ledger` +
  `ReportService.bank_ledger_report()` — Excel/CSV/PDF with EXACTLY the
  bank-ledger sheet columns (deposit tracker G–K + N, column N confirmed as
  Deposit Amount): **Supplier, Supplier Proforma Invoice No., Sunshine
  Invoice No., Selected Customer, Currency, Deposit Amount**.
- Same date-range filters as the other reports (by created date);
  merchandisers scoped to their own requests, other roles see all.
- Reports page: new "Bank Ledger" report type card with its column list —
  the generic download handler needed no changes.
- Tests (`test_bank_ledger_report.py`, 2 new): exact header order + row
  values from a seeded request; merchandiser scoping.

## Phase 8 — Auto-reload (item 4) · IMPLEMENTED (8 Aug 2026)

Polling, not websockets — fits the existing PWA/API architecture; the queue
pages already polled, the rest of the app now follows:
- **Global defaults** (`Providers.tsx`): `refetchOnWindowFocus: true` and
  `refetchOnMount: true` (both previously disabled — the root cause of "no
  autoreload in the entire app"); staleTime 5 min → 60 s.
- **Request lists** (`useRequests`, `useRequestsPaginated` — merchandiser
  My Requests, accounts Hold/Rejected/Cancelled/All tabs): 30 s poll +
  refetch-on-focus (`keepPreviousData` prevents flicker).
- **Request detail** (`useRequest`): 30 s poll — another user's tranche
  payment or hold shows up while the page is open.
- **File remarks list**: 30 s poll.
- Already live before this phase: pending queue, queue KPIs, HoM queue,
  my-activity, notifications (30 s each). Masters and analytics stay at
  5 min staleness — they rarely change.

### Verification
- `pytest tests/unit -q` — 257 passed.
- `npx tsc --noEmit` — clean.
- No new migration (head stays 0029).

---

# Batch complete — all 19 UAT points implemented

| Phase | Points | Migration |
|---|---|---|
| 1 | 9, 11, 15, 16 | — |
| 2 | 12, 17-validation, 18 | **0028** (status enum + trigger) |
| 3 | 5, 8, 13, 17-KPI, 19 | — |
| 4 | 6, 7, 10 | — |
| 5 | 2, 3 | — |
| 6 | 14 | **0029** (file-remark decisions) |
| 7 | 1 | — |
| 8 | 4 | — |

Deploy checklist:
1. `cd backend && alembic upgrade head` — applies **0028 → 0029**.
2. Deploy backend + frontend together (new endpoints: `/requests/{id}/reject`,
   `/requests/queue-kpis`, `/masters/suppliers/{id}/exposure`,
   `/file-remarks/{id}/approve|reject`, `/reports/bank-ledger`; removed:
   `/file-remarks/{id}/resolve`).
3. Final state: 257 backend unit tests green, `tsc` clean.

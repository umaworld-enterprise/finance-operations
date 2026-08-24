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

## Follow-up (10 Aug 2026) — one-click TT copy upload

The tranche card's two-step upload (Choose File → "No file selected" →
separate Upload TT Copy button) was replaced with a single always-enabled
**Upload TT Copy** button: it opens the file picker directly and the upload
starts the moment a document is chosen (same 10 MB / pdf-png-jpeg
validation, button shows "Uploading…" while in flight). Applied to both
upload sites in `TrancheList.tsx` — the unpaid-tranche flow and the
legacy paid-without-TT flow. Frontend-only; `tsc` clean.

## Follow-up (10 Aug 2026) — merchandiser dashboard buckets sum to Total

Gap: the merchandiser cards (Total / Pending / Processed / Cancelled) and
tabs never added up to the Total — **Rejected** had no card or tab, there
was no On Hold card, and awaiting-HoM / reopened requests were counted in
Total but appeared in no bucket at all. Fixed in `merchandiser/page.tsx`:

- Every status now lives in exactly one bucket (single source:
  `TAB_PARAMS`, reused verbatim for the card counts so cards and tabs
  always agree): **Pending** (pending_payment + pending_hom_approval +
  reopened), **On Hold** (both holds), **Processed**, **Rejected**
  (rejected_by_hom + rejected_by_accounts), **Cancelled** (both cancels).
- Six cards (Total + the five buckets, accounts-style grid) and six tabs,
  each tab showing its count — the five bucket figures sum to Total.
- Frontend-only; `tsc` clean.

## Refinements (10 Aug 2026) — five follow-ups on delivered items

1. **Item 5 (KPIs):** card subtext is now plain **"YTD"** (was
   "FY 2026–27 to date"). The FY window itself is unchanged.
2. **Item 3.x (tranche payment flow):** the **Save Details button is
   gone** — the payment-details form is a draft held by `TrancheList`, and
   **Mark Paid saves the filled details and pays in one action** (details
   PATCH then pay, sequentially). Mark Paid enables once the TT copy is
   uploaded and date + bank are filled; readiness item reworded to
   "Payment details filled"; confirm-dialog and toast wording updated.
3. **Item 14 (file remarks):** the New File Remark form is now visible to
   **merchandisers only** — super admin also lost it (previously kept for
   support); every decider role sees just Open Remarks + History.
4. **Merchandiser buckets:** verified cards and tabs carry the identical
   six buckets with counts (Total/All, Pending, On Hold, Processed,
   Rejected, Cancelled) — delivered by the 10 Aug bucket fix above.
5. **Merchandiser Pending card:** subtext removed entirely (was
   "Awaiting accounts", then "Approval or payment awaited").

Frontend-only; `tsc` clean; backend flow unchanged (the pay endpoint's
server-side readiness gate still requires saved details + TT copy — Mark
Paid now performs the save itself).

## Follow-up (10 Aug 2026) — HOM field visibility + rejection notifications

1. **HOM detail missing amounts (root cause found):**
   `FIELD_VISIBILITY_DEFAULTS` had NO `head_of_merchandiser` role at all,
   and `/requests/my-field-visibility` resolves unknown roles to False — so
   HOM saw none of the gated fields (deposit amount, %, total invoice,
   creator info, status history, the whole analytics card). Fixed:
   - `head_of_merchandiser` added to every defaults row (mirrors
     accounts_team — HOM approves what Accounts pay).
   - `get_field_visibility` now merges the stored config OVER the defaults,
     so configs saved before a role/field existed inherit defaults for the
     missing keys instead of hiding everything.
   - The admin Field Visibility matrix gained a "Head of Merchandiser"
     column so admins can manage it.
2. **Rejections notify HoM at BOTH levels:** request-level already did
   (Phase 2); `notify_tranche_rejected` now fans out to every active HoM
   as well as the raising merchandiser — reason included, per-audience
   deep links (`/merchandiser/{id}` with the add-replacement prompt vs
   `/hom/{id}`). Web + app parity verified by construction: both notifiers
   use `_deliver_to_users`, which writes the bell row AND sends the
   identical payload via Web Push to every subscription of each recipient
   (dead subscriptions pruned). Matrix updated; test extended
   (`test_tranche_rejected_notifies_merchandiser_and_hom`).

257 backend tests green; `tsc` clean; no migration.

## Follow-up (10 Aug 2026) — Supplier Default History panel rework

All in `SupplierDefaultHistory.tsx` (shared by HoM, Accounts and
Merchandiser detail views):
1. The amber "Active flag: … — outstanding … (flagged …)" box is removed —
   the flag details remain in the history table below.
2. Active-flag wording replaced (rendered red): *Red flag: this supplier
   has been listed under "Default Advance Payment List". Kindly review its
   history before making any decision.*
3. Live Exposure's "Every open file… Total: …" line replaced by a
   currency-segregated KPI table (one column per currency):
   - **Existing Exposure** (Overdue payments + Payments in process) — all
     open files EXCLUDING the request currently being viewed;
   - **Potential Exposure after approving this request** — Existing plus
     this request's deposit (row shown only when a request context exists).
   The three detail pages now pass the viewed request (id, deposit amount,
   currency) into the panel for this computation.

Frontend-only; `tsc` clean.

## Follow-up (10 Aug 2026) — "Amount Payable" column

New shared helper `amountPayable()` in `lib/utils.ts`: the sum of a
request's UNPAID tranches (paid are out the door, rejected don't count;
legacy rows without tranches fall back to the full deposit until
processed). Rendered right before the Deposit column in:
- Accounts queue: both pending buckets (0–10 / >10 days), the On Hold tab
  (via `StatusTable`'s new `showPayable` prop) and All Requests — desktop
  columns + mobile card "Payable:" line.
- Merchandiser Request History (`RequestsTable`).
Deliberately NOT shown on Rejected/Cancelled tabs (closed files) or the
HoM queue (nothing paid yet — payable would always equal the Amount
column). Frontend-only; `tsc` clean.

## Follow-up (10 Aug 2026) — search, sort & pagination on every table

New reusable kit: `useClientTable` hook (`hooks/useClientTable.ts` —
case-insensitive substring search over declared fields, pluggable sort
comparators, client pagination with page-clamping) + `TableControls`
component (search box + sort dropdown; pairs with the existing
`Pagination`). Applied to every table that lacked controls:
- **File Remarks** — Open Remarks and Remark History (search by request #,
  file numbers, category, raiser, status; sort newest/oldest/request #;
  20/page).
- **Supplier Risk (finance)** — defaulted-supplier table (search supplier/
  reason/status; sort by flag date, supplier, outstanding; 20/page).
- **Admin Users** — sort (name/role/recent login) + pagination added to the
  existing search (25/page).
- **Admin Banks** and **Admin Payment Terms** — search + sort + pagination
  (20/page; payment-term row numbers stay absolute across pages).
- **Accounts pending buckets** (0–10 / >10 days) — client pagination per
  bucket (50/page, shown only when needed); the page-level search and sort
  already applied before the split.

Already covered (unchanged): merchandiser dashboard, HoM queue, accounts
status tabs (server pagination + search + sort), audit log (server filters
+ pagination), notifications, analytics tables (ShipmentsTable, drill,
supplier detail, NPA panel), admin overview. Contextual sub-tables inside
detail panels (Supplier Default History, tranche list) intentionally keep
no controls. Frontend-only; `tsc` clean.

## Follow-up (10 Aug 2026) — file-remark parent reference + weekly label format

1. **Old file input removed** from the Invoice amount change form — the old
   file reference is now server-derived from the selected request (sunshine
   invoice number → proforma number → request number fallback), exactly
   like the old amount. `FileRemarkCreate` no longer accepts
   `old_file_number` at all.
2. **Splits show their parent**: the derived parent reference is recorded
   for BOTH categories, so the history's Details cell for a split now reads
   "From {parent} (amount)" above the "→ target (amount)" rows. Older rows
   stored without a parent fall back to the request number in the UI.
3. **Analytics weekly labels** (Outstanding tracker + weekly deposit
   tracker): `10/08/2026 to 16/08/2026` → **`10-Aug-2026 to 16-Aug-2026`**
   (`%d-%b-%Y`), removing day/month ambiguity.

257 backend tests green (file-remark + tracker label tests updated);
`tsc` clean; no migration.

## Follow-up (10 Aug 2026) — refinements: flag table removed + remaining table controls

1. **Supplier Default History card**: the flag-history table
   (Flagged / Reason / Outstanding / Status) is removed — the card now
   carries only the red-flag line and the Live Exposure section. Full flag
   records remain on the Supplier Risk page.
2. **Search/sort sweep completed** — remaining gaps closed:
   - Analytical Snapshot (`ShipmentsTable`, accounts + HoM dashboards):
     search (request #, invoice #, supplier, status) + sort (most delayed /
     ETD / amount / supplier) on top of its pagination.
   - Notifications: search box filtering the loaded page (feed stays
     server-paginated).
   - Merchandiser "All Updates" activity: search + sort + pagination
     (25/page).
   - Audit Logs: free-text search over the loaded page (entity, field,
     values, user, IP) alongside the existing server filters + pagination.
   Note: controls added in the previous sweep render ABOVE each table (and
   once above the tabs on the queue pages) — a hard refresh/redeploy is
   needed for the PWA to pick up the new bundle.

257 backend tests green; `tsc` clean.

## Follow-up (10 Aug 2026) — NPA table controls + split parent shows invoice no.

1. **Non-Performing Assets** panel: both tables gained search + sort —
   Overdue Suppliers (search supplier/reason; sort by max overdue, overdue
   requests, supplier) and Merchandiser Performance (search name/email;
   sort by overdue count, total requests, name). Pagination they had.
2. **Split parent = sunshine invoice number**: `FileRemarkResponse` now
   carries the parent request's CURRENT `sunshine_invoice_number`, and the
   "From {parent}" line prefers it over the stored parent reference (which
   itself falls back to the request number only for legacy rows or files
   without an invoice number). Covers remarks created before the derived
   parent existed and invoice numbers edited after the remark was raised.

Backend tests green; `tsc` clean.

## Follow-up (11 Aug 2026) — exposure KPIs count processed files only

Live Exposure refinement: **Existing Exposure** now sums only
`payment_processed` files (money actually paid out, goods not shipped) —
pending/held files are commitments, not exposure, and no longer inflate the
figure (they remain visible in the graced-ETD breakdown tables).
**Potential Exposure** stays Existing + the viewed request's deposit. A
currency column appears only when it has processed exposure or the viewed
request would add that currency — e.g. a supplier with only a PENDING GBP
file shows no GBP column at all unless the request being approved is GBP.
Frontend-only; `tsc` clean.

## Follow-up (11 Aug 2026) — bucket-scoped Amount Payable in the pending tables

The two pending tables' Amount Payable column is now scoped to each
table's own tentative-date window instead of the request's total unpaid:
- **0–10 days table**: sums only the unpaid tranches whose tentative date
  falls within the next 10 days (past-due dates included).
- **> 10 days table**: sums only the unpaid tranches due after the window
  (undated tranches included).
So a request with one tranche due tomorrow and one due next month shows
just tomorrow's amount in the 0–10 table. The On Hold / All / merchandiser
tables keep the total-unpaid figure. Frontend-only; `tsc` clean.

## Follow-up (11 Aug 2026) — Existing Exposure recalibrated

Existing Exposure = **Overdue Payments** (processed, graced ETD passed,
goods not shipped) + **Payments in Process** (processed and still inside
the grace window, PLUS requests already HoM-approved and sitting in the
payment queue — `pending_payment` — even before Accounts process them).
Requests awaiting HoM approval, on hold or reopened remain excluded from
the KPI (visible in the breakdown tables). Potential Exposure and the
currency-column rule unchanged. Frontend-only; `tsc` clean.

## Follow-up (11 Aug 2026) — pending queue back to a single table

The "Tentative Payment in > 10 Days" table was removed on client request —
the Pending tab is a single "Pending Payment" table again holding ALL
pending requests (so later-dated files don't disappear), keeping the
Tentative Payment column for the next due date. **Amount Payable keeps the
standing 11 Aug rule**: the column (headed "Amount Payable (0–10 days)")
sums only the unpaid tranches due within the next 10 days, past-due
included — a request with nothing due soon shows 0. (An initial revert of
this to total-unpaid was a mistake and was corrected the same day.)
Frontend-only; `tsc` clean.

## Follow-up (11 Aug 2026) — Invoice Change rename, From/To details, Accounts invoice editing

1. Category label renamed **"Invoice amount changes" → "Invoice Change"**
   (form dropdown, tables, notification/audit wording via the shared label
   maps; stored category value unchanged).
2. Remark history Details for an Invoice Change now reads explicitly
   **From {old file} (amount)** / **To {new file} (amount)** on separate
   lines (From falls back sunshine → stored parent → request number).
3. Invoice-number editing extended to the **Accounts Team** from the
   payment-queue request view (client-confirmed: BOTH sunshine and
   proforma numbers, on any request — the "changed in whole" wording is
   the business reason, not a system gate). Endpoint guard relaxed from
   Super Admin-only to {super_admin, accounts_team}; per-field audit and
   duplicate validation unchanged. The Invoice Numbers card on
   `accounts/[id]` now shows for Accounts with updated helper text.

257 backend tests green; `tsc` clean.

## Follow-up (11 Aug 2026) — MAJOR: defaulter/overdue logic recalibrated

`etd_grace_overdue_days` (the defaulter metric) now accrues ONLY when all
three hold: **advance PAID** (payment_date set) + **graced ETD surpassed**
+ **shipment NOT made**. Changed in one place — `analytics/engine.compute()`
— and inherited by everything that keys off `etd_grace_overdue_days > 0`:
auto-flagging ("Auto-flagged: Nd past ETD grace"), NPA overdue suppliers,
delay report, analytics drill/summary, supplier exposure overdue column.
- Unpaid files never accrue overdue (no money out), even past grace.
- Shipping clears the defaulter state (overdue → 0); the lateness history
  stays visible via `actual_etd_overdue_days` (signed, ship-frozen) and
  cost of fund, which are unchanged.
- Exposure panel no longer renders "0d overdue" (shows — instead).
- Deploy note: stored snapshots recompute on the periodic snapshot job and
  on per-request reseeds — figures update as the job runs, not instantly.

Tests: engine tests rewritten around the three-condition rule (paid+
unshipped accrual, shipment clears, unpaid never accrues, delayed/critical
thresholds) — 260 backend tests green; `tsc` clean.

## Follow-up (11 Aug 2026) — "Advance Payment" module sub-header in the sidebar

An **Advance Payment** sub-header now sits directly below "Menu", grouping
all current items as the first module — future modules (e.g. Logistics)
get their own sub-header alongside. Styling: slightly brighter/bolder than
the "Menu" label so it reads as a module title. Frontend-only; `tsc` clean.

## Banking module (12 Aug 2026) — bank statement upload + AI extraction + dashboard

New standalone module (client decisions: AI vision extraction; **super
admin only** for now; no ADT reconciliation in v1; dashboard scope at my
discretion). Sample analysed: Citi "Asia Account Statement Report" — its
PDFs have NO usable text layer (fonts without unicode maps), so extraction
is vision-based.

**Migration `0030_bank_statements.py`** (head **0030**):
`bank_statements` (header/summary + status processing/extracted/failed +
extraction_note; unique account+period), `bank_transactions` (date, type
line as category, reference, detail, debit/credit; CASCADE),
`bank_daily_balances` (per-day closing balance rows; CASCADE).

**Backend:**
- `AIClient.chat_vision()` added (OpenAI + Claude wrappers; Groq raises
  with a switch-provider message). Reuses the admin-configured provider/
  key/model from AI Settings.
- `bank_statement_service`: PyMuPDF renders pages (150 dpi, ≤80 pages) →
  one vision call per page → strict-JSON parse (`parse_page_json`) →
  aggregate → **integrity check** (beginning − debits + credits vs the
  statement's own ending balance; result stored in extraction_note, loud
  MISMATCH wording when off) → persist. Duplicate account+period uploads
  are refused at extraction time. Runs as a BackgroundTask with its own
  session; failures flip the row to `failed` with the error.
- API `/bank/statements` (super admin): POST upload (PDF ≤15 MB, answers
  immediately in `processing`), GET list, GET detail (transactions +
  daily balances), DELETE (re-upload path). Upload/delete audited.
  `pymupdf` added to requirements.

**Frontend:**
- Sidebar: new **Banking** module sub-header (data-driven `module` field on
  nav items) with "Bank Statements" (super admin), alongside Advance
  Payment.
- `/bank`: one-click PDF upload (TT-copy pattern), statements table
  (status pill polls every 5 s while processing; search/sort/pagination),
  delete-with-confirm, and a Month-over-Month table across extracted
  statements (opening/closing/net per account).
- `/bank/[id]` dashboard: integrity-check banner (green/amber),
  six KPIs (Opening, Closing, Total Debits, Total Credits, Net Movement,
  Transaction count), **Daily Closing Balance** line chart (recharts),
  **Breakdown by Transaction Type** (Import/Export bills, check clearing,
  charges, interest… with counts and debit/credit totals), and the full
  transaction table with search/sort/pagination.

**Tests** (`test_bank_statements.py`, 7 new — 267 total): JSON parsing,
decimal/date safety, integrity outcomes, end-to-end extraction against a
fake vision client (rows + balances persisted, header populated, integrity
passed), mismatch flagged loudly, provider failure → `failed`, duplicate
period refused.

**Deploy:** `pip install -r requirements.txt` (pymupdf) +
`alembic upgrade head` (0030). Extraction requires an OpenAI or Claude key
in AI Settings — Groq is text-only.

## Follow-up (12 Aug 2026) — Accounts' Analytics Snapshot missing fields

The Analytics Snapshot card on the accounts request view silently dropped
**Cost of Fund** and **Payment to Request Days** — the field-visibility
DEFAULTS had both set to False for `accounts_team`. Flipped to True for
accounts AND head_of_merchandiser (parity: HoM approves what Accounts pay).
Note for existing environments: if an admin ever SAVED the Field Visibility
matrix, the stored config overrides these defaults per field — toggle the
two rows on in Admin → Field Visibility there. Backend-only; 267 tests
green.

## Follow-up (19 Aug 2026) — Banking module opened to Accounts team

The Banking module (Bank Statements) is no longer super-admin only: the
**accounts team gets full access** — upload, dashboards, and delete /
re-upload — per the new requirement. Backend router now guards with
`RequireAccounts` (super_admin + accounts_team) instead of
`RequireSuperAdmin`; frontend sidebar entry and both bank pages'
`RoleGuard`s include `accounts_team`. No migration; deploy backend and
frontend together so the sidebar link and the API gate match.

## Follow-up (19 Aug 2026) — Merchandiser can add tranches after a payment

User report: after a tranche was paid, the merchandiser lost the Add Tranche
button. Validated as intended behaviour of the old rule (item 2.3: ANY
accounts write froze all merchandiser tranche changes), then relaxed per the
new requirement (**add + edit/delete unpaid** chosen):

- **Per-tranche locks replace the request-wide freeze.** A tranche Accounts
  has started working on — PAID, TT copy uploaded, or payment details
  recorded — is locked against merchandiser edit/delete
  (`_assert_tranche_untouched_by_accounts`). Untouched unpaid siblings stay
  editable/deletable, and ADDING tranches stays open, while the request is
  still pending. The invoice-total ceiling still applies.
- **Request-wide accounts writes still freeze everything**: a
  payment_details row (ship-date / legacy paths) or a completed invoice
  adjustment (`accounts_touched_reason`, now narrowed to those two). The
  rejection deadlock-breaker (adds allowed while a REJECTED tranche exists)
  is unchanged.
- `/tranches/modifiable` now answers `modifiable: true` in the
  paid-some-tranches case; the frontend derives per-row locks from the
  tranche's own fields (`tt_copy_url` / `payment_date` / `bank` /
  `payment_reference_number`) and shows "In processing by Accounts — locked"
  on rows it can't touch.

Tests: 268 passing — new `test_paid_tranche_no_longer_freezes_siblings`;
`test_tt_copy_locks_only_that_tranche` and
`test_tranche_payment_details_lock_only_that_tranche` rewritten from the old
blanket-freeze assertions; the rejection-unlock test now freezes via a
request-wide payment row. No migration.

## Follow-up (19 Aug 2026) — Sunshine Invoice No. on Live Exposure overdue rows

The Live Exposure "Graced ETD passed" (overdue) table now shows the
**Sunshine Invoice #** column between Request # and Deposit. The exposure
endpoint (`/masters/suppliers/{id}/exposure`) returns
`sunshine_invoice_number` on every row; the frontend renders the column on
the overdue table only. One shared component, so it applies to every role
that sees the panel (HoM, Accounts, Merchandiser detail views). No
migration; 268 tests green.

## Follow-up (19 Aug 2026) — File Remarks: request links, split balance, locked Invoice Change amount

Three changes on the File Remarks module:

1. **Request # is a link** in Open Remarks and Remark History — merchandisers
   land on their request view (`/merchandiser/{id}`), accounts / finance /
   super admin on the payment-queue view (`/accounts/{id}`).
2. **Balance after split** — the Details cell on split remarks shows
   "Balance on {parent}: X" (old amount − split total), always, including
   0.00 as explicit full-allocation confirmation. Same shared cell for all
   roles. The New File Remark split form also shows "Balance left" live next
   to the split total. Legacy rows without a stored old amount show no
   balance line.
3. **Invoice Change amount locked** — a whole-invoice change keeps the
   value: the New file amount pre-fills from the selected file and is
   read-only; the server now DERIVES new_amount (= the file's deposit
   amount) and no longer accepts it from the client (schema field removed,
   ceiling check moot). Only the new file number is typed.

No migration; 268 tests green; deploy backend + frontend together (the
create payload no longer carries new_amount).

**Format update (same day):** split details now read
`From Invoice {parent}: {amount} ({currency})` /
`- to Invoice {file}: {amount} ({currency})` /
`Balance in Invoice {parent}: {amount} ({currency})`. The remark response
carries the request's `currency` for this (new field on
FileRemarkResponse). Invoice Change rows keep their From/To layout.

## Follow-up (19 Aug 2026) — Back button on the accounts request summary

The accounts request summary now offers two ways back: a new **Back**
button (browser history — returns to wherever the user came from, e.g. a
File Remarks link) alongside the existing **Back to queue** fixed jump to
the dashboard sheet. Frontend-only.

## Follow-up (19 Aug 2026) — Adding a tranche REOPENS a completed file

New requirement (after the single-tranche file on the screenshot closed on
its first payment): the merchandiser can add tranches to a
**payment-processed** file — doing so REOPENS it.

- **New status transition** `payment_processed → pending_payment`
  (merchandiser + super admin only), fired inside
  `TrancheService.add_tranche`, not a standalone action. All three
  status-rule locations updated: `status_transitions.py`, the Postgres
  trigger (**migration 0031**), enums unchanged.
- On reopen: request returns to the payment queue, unlocks, StatusHistory +
  audit written, and the payment_details completion marker steps back
  (payment_status cleared; the paid-so-far payment_date is kept for the
  record). Paying the new final tranche completes and locks the file again,
  re-deriving the marker.
- Ceiling unchanged: total tranches ≤ invoice total. Paid tranches stay
  immutable; the new unpaid tranche is a normal editable pending tranche.
- `accounts_touched_reason` narrowed once more: a payment row counts as a
  request-wide touch only when it shows real accounts activity (processed
  status, ship date, legacy TT copy, bank/reference/remarks) — a bare row
  holding only the paid-so-far date (what a reopened file keeps) does not
  freeze the merchandiser.
- Frontend: merchandiser detail keeps the tranche list interactive on
  processed files; `/tranches/modifiable` answers `can_add: true` there;
  the amber notice explains that adding reopens the file (the rejection
  wording now only shows when a rejected tranche actually exists).

Tests: 272 passing — reopen round-trip (pay → add → edit → pay →
completes again), ceiling + role guards on reopen, transition-map cases
(the old "processed → pending is invalid" test now asserts the opposite);
`_add_payment_row` fixture carries a ship_date so request-wide freeze tests
still exercise a genuine touch.

Deploy checklist:
1. `cd backend && alembic upgrade head` — applies **0028 → 0029**.
2. Deploy backend + frontend together (new endpoints: `/requests/{id}/reject`,
   `/requests/queue-kpis`, `/masters/suppliers/{id}/exposure`,
   `/file-remarks/{id}/approve|reject`, `/reports/bank-ledger`; removed:
   `/file-remarks/{id}/resolve`).
3. Final state: 257 backend unit tests green, `tsc` clean.

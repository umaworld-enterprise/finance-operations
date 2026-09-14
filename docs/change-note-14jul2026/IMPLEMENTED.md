# Implemented — Process Change Note (14 July 2026)

Maps each change-list ID from [CHANGE-LIST.md](CHANGE-LIST.md) to the code that
satisfies it. All work was done on `development`, July 30 2026, in six phases.
Verification per phase: `backend pytest tests/unit` green (181 tests at
completion) and `frontend npx tsc --noEmit` clean.

Everything under `hf_space/` was left untouched (stale fork, per ground rules).

---

## A. §4 tranche table

### A1 — Tentative payment date defaults to today · DONE (Phase 1)
- `frontend/src/lib/utils.ts` — new `todayLocalISO()` (local-timezone
  `YYYY-MM-DD`; deliberately not `toISOString()`, which shifts a day on
  negative UTC offsets).
- Seeded in all four spots: `merchandiser/new/page.tsx` (defaultValues +
  `append`), `form/page.tsx` (defaultValues + `appendTranche`).
- Required asterisk added to both tranche date labels (they are plain
  `<p>`/`<label>` elements — the shared `Field` only renders its own asterisk
  when it owns the label).
- `payment_tranches.tentative_payment_date` nullability untouched (legacy rows
  stay NULL). No migration.

### A2 — Tranche amount shows the deposit currency · DONE (Phase 1)
- `currencyDisplayLabel()` promoted from `form/page.tsx` to
  `frontend/src/lib/utils.ts` (`CNY → "CNY (RMB)"`, null-safe → "—") and used
  everywhere a raw code was shown: both create forms (amount labels, currency
  dropdowns, totals), `TrancheList.tsx` edit mode, the Accounts "Currency"
  column, and the Outstanding tab headers (`analytics/page.tsx`).
- Merchandiser form: tranche section is a `<fieldset disabled>` until a
  currency is selected; all three `|| "USD"` fallbacks removed.
- `formatCurrency()` widened to `string | null` — null/empty currency renders a
  plain number instead of pretending USD (also fixes legacy rows that rendered
  "1,000.00 null").
- No per-tranche currency column added (by design).

### A3 — Tranche edit notifies Accounts · already built, no change

---

## B. §7 Adjust Invoices

### B1 — Shipped requests excluded from Adjust Invoice · DONE (Phase 5)
Rule key: `payment_details.ship_date IS NOT NULL` (not `estimated_etd`, not
the field C5 deleted).
- `backend/app/services/adjustment_service.py` —
  `supplier_tranche_options` outer-joins `payment_details` and requires
  `ship_date IS NULL` (outer join keeps requests with no payment row);
  `_assert_not_shipped()` re-asserts server-side in `create` **and** at
  approve time, on BOTH source and destination requests, raising
  `BusinessRuleError` naming the request and ship date.
- `frontend/.../adjust-invoices/page.tsx` — permanent note under the supplier
  picker explaining why shipped requests are missing.
- Tests: shipped request in neither list; NULL-ship_date partial row does NOT
  exclude; create rejected for shipped source and shipped destination.

### B2 — Adjust Invoice changes push to Accounts Team · DONE (Phase 6)
- `backend/app/services/notification_service.py` — types
  `adjustment_requested` (merchandiser-raised, pending) and
  `adjustment_recorded` (accounts-raised, completed);
  `notify_adjustment_created()` fans out to every active `accounts_team` user
  **excluding the actor**, mirroring `notify_tranche_updated`.
- `backend/app/api/v1/adjustments.py` — `BackgroundTasks` wired into create.

### B3 — Merchandiser adjustment requests + Accounts queue · DONE (Phase 6)
Scope confirmed with the client before building: yes, merchandisers raise;
Accounts decides; reason mandatory on approve AND reject.
- **Roles** — `_DECIDER_ROLES` (accounts_team, super_admin) vs
  `_REQUESTER_ROLES` (+ merchandiser) in `adjustment_service.py`;
  `api/v1/adjustments.py` write roles include merchandiser, history for
  merchandisers is scoped to `performed_by = self`; `Sidebar.tsx` and the
  page's `RoleGuard` include merchandiser.
- **Status on create** — merchandiser → `PENDING_APPROVAL`; accounts/super →
  `COMPLETED`. No migration (statuses pre-existed in enum + PG type, 0018).
- **Balance safety (critical)** —
  `tranche_repo.AdjustmentRepository.adjusted_out_total` now counts
  **COMPLETED only** (previously pending reserved balance — inverted).
  Pending rows consume nothing; `approve()` re-runs every create-time
  validation (paid source, unpaid destination, same supplier, B1 ship-date,
  balance) under the source-tranche row lock. Double-spend covered by test:
  two pending 700s on a 1000 tranche → first approval completes, second fails.
- **Reason** — service rejects merchandiser-raised creates without a non-blank
  reason; `AdjustmentDecision` schema (`reason`, min_length 1) backs both
  approve and reject.
- **Endpoints** — `GET /adjustments/pending` (deciders + finance_admin
  read-only, oldest first), `POST /adjustments/{id}/approve`,
  `POST /adjustments/{id}/reject`. `status` exposed on `AdjustmentResponse`
  (already was) and shown in the UI.
- **Notifications** — `adjustment_decided` back to the raiser with the reason;
  `BackgroundTasks` on create/approve/reject.
- **UI** — "Accounts Queue" card above History (approve/reject via the shared
  mandatory-reason `DecisionDialog`), Status pill column in History,
  merchandiser-specific form copy ("New Adjustment Request", required reason,
  pending-aware success toast).
- **Audit** — decisions write a `status` row on the adjustment (reason
  embedded) plus `invoice_adjustment_approved/_rejected` rows on BOTH
  requests, matching create's three-row pattern. Create wording:
  "requested" (pending) vs "reallocated" (completed).

---

## C. Pages 5–6, points 1–7

### C1 — Flagged-supplier submission message · DONE (Phase 1 + follow-up)
- `merchandiser/new/page.tsx` — create result captured; toast branches on
  `current_status === "pending_hom_approval"` → "Request sent to the Head of
  Merchandiser for approval." else "Request submitted."
- "Head of Merchandising" → "Head of Merchandiser" in
  `SupplierDefaultAlert.tsx` and the override banner.
- **Follow-up (client-identified gap, 30 Jul 2026): the PUBLIC form's success
  screen had the same defect** — it always said "will be reviewed by the
  accounts team" even for flagged-supplier submissions, and the backend
  response message at `api/v1/public_form.py` hardcoded the same claim.
  Fixed at both layers: `PublicSubmissionResponse` now carries
  `current_status` (nullable, backward-compatible) and a routing-aware
  message; `form/page.tsx` branches the success card — flagged route shows
  "Request Sent for Approval" / Head-of-Merchandiser copy, normal route keeps
  the accounts-team copy.

### C2 — One request-ID nomenclature · DONE (Phase 1)
- `lib/utils.ts` — `requestDisplayNumber` returns `request_number` only.
- Separate "Invoice #" column/line (em-dash when null) added to all five list
  surfaces: HOM queue, `RequestsTable.tsx` (hidden on xs), Accounts
  Pending/On Hold/All (desktop column + mobile-card line each), Admin
  overview. Header/cell/skeleton/colSpan counts kept in sync.
- `requestMatchesSearch`, backend notifications, emails, report exports —
  untouched (already correct).

### C3 — HoM reason mandatory on approve and reject · DONE (Phase 2)
- `backend/app/schemas/deposit_request.py` — new `HomDecisionRequest`
  (`remarks: str, min_length=1`); the shared `StatusChangeRequest` untouched.
- Both `hom-approve` / `hom-reject` endpoints use it → 422 on missing/empty.
- Frontend — shared `components/hom/DecisionDialog.tsx` (required textarea,
  Confirm disabled while blank, state reset on close) used by both the queue
  page and detail page for approve AND reject; `useHomApprove`/`useHomReject`
  and the two `requestService` methods take `remarks: string` (non-optional).
- Known nuance: `min_length=1` accepts a whitespace-only string at the API
  layer (UI trims); flagged to the client, left as specified.

### C4 — HoM decision pushes to the merchandiser · DONE (Phase 2)
- `notification_service.py` — `hom_approved`/`hom_rejected` types,
  `build_hom_decision_message()` (request number + reason, deep-link
  `/merchandiser/{id}`), `notify_hom_decision()` using `_find_target_user`
  (handles `created_by` and public-form `submitter_email`).
- Both HOM endpoints take `BackgroundTasks` and enqueue after transition.
  Implemented for approve as well as reject.

### C5 — Estimated Shipment Date section removed · DONE (Phase 4, column drop deferred)
- **Live schema verified first** (read-only query against the Supabase DB in
  `backend/.env`): column already nullable, all rows NULL. Note: that DB's
  `alembic_version` was `0019` at the time — 0020/0021 pending deploy.
- **Migration A already existed**: `0021_relax_deposit_requests_nullability.py`
  (commit 76adeaa) performs the `DROP NOT NULL`. No new migration written.
- Removed from: frontend (`accounts/[id]` card + handler, `RequestsTable`,
  Accounts pending table, `merchandiser/[id]`, `types/index.ts`,
  `requestService.ts`, `admin/form-config` field + default-required list) and
  backend (`schemas/deposit_request.py` ×3, `api/v1/public_form.py` ×2,
  `services/bi_service.py` text-to-SQL prompt schema,
  `scripts/migrate_csv.py` import, `models/deposit_request.py`).
- Untouched, as required: `payment_details.ship_date`,
  `POST /requests/{id}/payment/ship-date`, PaymentForm's Ship Date block.
- Grep for `estimated_shipment_date` now hits only migrations, these docs,
  and `hf_space/`.

### C6 — No tranche paid without a TT copy · DONE (Phase 3)
- `tranche_service.pay_tranche` — guard after the already-paid check:
  falsy `tt_copy_url` → ConflictError "cannot be marked paid until its TT copy
  is uploaded". Guard runs before the pending-payment status check.
- **Ordering trap** solved by reordering `attach_tt_copy`: tt_copy_* fields
  (+ audit) are written BEFORE the auto-pay, so the compliant flow satisfies
  the guard; failures roll back atomically.
  `test_tt_upload_on_unpaid_tranche_auto_pays` passes unchanged.
- `payment_service.process_payment` — the bulk mark-all-tranches-PAID loop is
  deleted; unpaid tranches remaining → ConflictError. Tranche-less legacy
  requests still process.
- `POST /requests/{id}/tranches/{tranche_id}/pay` **deleted** (client
  confirmed) — TT upload is the only route to PAID; `pay_tranche` stays
  service-internal for `attach_tt_copy`. Dead frontend plumbing removed
  (`usePayTranche`, `requestService.payTranche`, Mark-Paid button + dialog).
- `TrancheList.tsx` — single "Upload TT Copy & Mark Paid" action; the
  paid-but-no-TT block retitled as legacy remediation.
- Tests updated via `_with_tt()` helper; new
  `test_pay_tranche_without_tt_copy_rejected`.

### C7 — Payment Details fields mandatory · DONE (Phase 3)
Four fields: Payment Date, Bank, Payment Reference Number, Payment Status.
- `schemas/payment.py` — inheritance inverted: `PaymentUpdate` is the
  permissive base (partial PATCH keeps working), `PaymentCreate` requires the
  four. `ShipDateUpdate` untouched.
- `payment_service.process_payment` — completeness gate names the missing
  fields. `set_ship_date` / `attach_tt_copy` remain exempt (partial rows are
  their design). **No DB NOT NULL** (would break those two paths).
- `PaymentForm.tsx` — four required zod fields; hidden bug fixed
  (`formState.errors` was never destructured, so messages never rendered);
  `values:` force-sync is safe because validation mode is onSubmit (legacy
  NULL rows don't error on render).
- Payment Status forces an explicit pick (client decision): the placeholder
  option is kept but `disabled` — removing it entirely would visually
  preselect "Processed" while the form value stayed empty.
- Behavioral note (flagged to client): "Save Details" POSTs → partial drafts
  can no longer be saved via the UI; switch the form to PATCH for existing
  rows if draft saves are ever needed.

---

## Deferred / follow-ups

1. **Migration B — `DROP COLUMN deposit_requests.estimated_shipment_date`.**
   Deliberately staged: write it only after 0021 is deployed everywhere
   (the inspected DB was still at 0019). Its `downgrade()` can only re-add the
   column as nullable — say so in the docstring. All code references are
   already gone, so the drop is a pure DDL change.
2. **0021's `downgrade()` is unsafe on live data** (pre-existing): it
   re-imposes NOT NULL on three columns whose rows are NULL. Fix before anyone
   ever downgrades past it.
3. **Adjustment decision metadata as columns** — `decided_by`, `decided_at`,
   `decision_reason` on `invoice_adjustments` would need a migration; today
   the decision reason lives in the audit trail and the notification only.
4. **Whitespace-only HoM/adjustment reasons** pass the `min_length=1` API
   check (UIs trim). Add strip-validators if raw-API hygiene matters.
5. **Not in scope, from the change list's "Not in the change list" section:**
   Outstanding tracker placement (sibling tab vs Analysis tab), and the latent
   `get_outstanding_tracker` merchandiser-scope leak if that section is ever
   granted to merchandisers at runtime.

## Post-note addition (CIO request, 30 Jul 2026)

**Onboarding Department: free text → dropdown.**
`frontend/src/app/onboarding/page.tsx` — the Department input is now a
`Select` over a fixed `DEPARTMENTS` constant (Merchandising, Accounts,
Finance, Management, IT, Other) with a disabled placeholder, still required.
Deliberately UI-only (client decision): the backend keeps `department` as a
free `String(100)` (`ProfileUpdate.department: str`, no migration), so
legacy free-typed values already in `users.department` stay valid and
extending the list is a frontend-only edit. Onboarding is the only entry
point for this field — Settings and admin pages never write it.

## Incidental fixes made along the way

- Baseline `npx tsc --noEmit` had 20 pre-existing errors (nullable-currency
  mismatches, `ReactNode` imported from `"next"`, missing HoM statuses in the
  activity page's border map, nullable `req.vertical`, a `BufferSource` cast
  in `push.ts`, readonly `TAB_PARAMS` typing) — all fixed in Phase 1 so the
  per-phase "tsc clean" acceptance was actually meaningful.
- Committing test modules (`test_hom_decision.py`,
  `test_adjustment_notifications.py`) got autouse wipe fixtures — the notify
  entry points open their own DB sessions, so those tests must commit, and
  committed rows otherwise leak across modules on the shared in-memory engine.

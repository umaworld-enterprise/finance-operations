# Implemented — CIO Change Batch (Aug 2026)

Running log, one section per phase. Same verification gates as the July batch:
`backend pytest tests/unit` green and `frontend npx tsc --noEmit` clean per phase.

**Deferred by the client:** Ship Date removal from the Payment stage — parked
until explicitly called; CoF freeze, delay analytics, and the Adjust-Invoice
shipped-exclusion continue to work unchanged.

---

## Phase 1 — Public form retired; authenticated requests only · DONE (1 Aug 2026)

The login-free `/form` page and its `/api/v1/public/*` endpoints are retired.
Deposit requests are now raised exclusively through the authenticated in-app
form.

**Backend** — `app/api/v1/public_form.py` rewritten to three stubs returning
**410 Gone** with a message pointing users to sign in
(`/public/masters`, `/public/form-config`, `/public/submit`). This also closes
a data exposure: `/public/masters` used to serve supplier/customer names and
flagged-supplier status without auth. Kept deliberately:
`DepositRequestService.create_public`, the `submitter_email` column and its
notification recipient resolution (legacy rows), the `public_form_fields`
SystemConfig rows, and the form-links table — nothing destructive, feature can
be revived.

**Frontend**
- `app/form/page.tsx` replaced with a static "Sign-in Required" notice card +
  link to `/login`; `app/form/[slug]/page.tsx` re-exports it, so every shared
  form link lands on the same notice. `form/layout.tsx` metadata updated.
- Middleware still exempts `/form` from the session gate — intentional: the
  page is a static explanation with no data behind it, which reads better than
  a silent bounce to /login for people holding old links.
- Admin overview: **Form Configuration** and **Form Links** quick-links
  removed. Both pages remain reachable by direct URL with a prominent
  **Deprecated** banner (client-approved "hide, don't delete" approach).

**Tests** — `tests/unit/test_public_form_submit.py` repurposed: all three
endpoints assert 410 + "retired"/"sign in" messaging. The old submit-path
tests were removed with the surface they tested (the service logic they
exercised is still covered by the request-creation tests).

**Follow-up candidates** (not done): delete `public_form.py`, the form-links
admin page/endpoints, and `admin.py`'s `public_form_fields` config endpoints
outright once the org confirms no shared links remain in circulation.

---

## Phase 2 — Duplicate invoice validation · DONE (1 Aug 2026)

Rule (client-confirmed): no two live requests may share a **Sunshine Invoice
No.** or a **Supplier Proforma Invoice No.** Case-insensitive, trimmed.
Requests that are cancelled (either side) or rejected by HoM do NOT block
reuse — their number may legitimately be re-raised.

**Live-data finding (why service-layer, not DB unique indexes):** a read-only
check of the production DB found one existing collision —
`AGV-0001` on both Dep-2026-0001 and Dep-2026-0002 — so partial unique
indexes would fail to build until that pair is resolved. Flagged to the
client; if the data is cleaned, indexes can be added as hardening later.

**Backend**
- `deposit_request_service.py` — `find_invoice_conflict(field, value,
  exclude_request_id)` + `_assert_invoice_numbers_unique(...)` raising
  `BusinessRuleError` (422) naming the conflicting request number. Wired into
  `create`, `create_public` (kept consistent even though the public surface is
  retired), and `update` (excluding the request's own row, so re-saving its
  own number is fine — covers the super-admin invoice editor and generic
  PATCH).
- `GET /requests/check-invoice?field=…&value=…` (authenticated, field
  whitelisted by regex) → `{duplicate, request_number}` for pre-submit UX.
  Registered before the `/{request_id}` route.

**Frontend** (`merchandiser/new/page.tsx` + `requestService.checkInvoiceNumber`)
- On blur of either invoice field: async check → inline warning under the
  field naming the conflicting request.
- On submit: both filled numbers are checked; any duplicate opens a blocking
  **"Duplicate Deposit Request"** modal (lists each conflict, "Back to form")
  and submission is stopped. A failed pre-check never blocks — the server
  re-validates on create regardless and its 422 surfaces as a toast.

**Tests** — `tests/unit/test_duplicate_invoice.py` (9): duplicate blocked on
either field, case-insensitive + trimmed, unique/empty values pass,
cancelled ×2 / rejected statuses don't block reuse, update-to-duplicate
blocked, self-update allowed, unknown field rejected.

---

## Phase 3 — Merchandiser module · DONE (1 Aug 2026)

### 3.1 Label rename
"Supplier Invoice No./Number" → **"Supplier Proforma Invoice No."** in the
request form (`NewRequestForm.tsx`) and "Supplier Proforma Invoice #" on the
merchandiser / HoM / accounts detail pages, incl. the super-admin invoice
editor. The deprecated form-config page and report export headers were left
as-is (dead surface / backend-driven respectively).

### 3.2 Form into the Merchandiser Queue (client choice: collapsible section)
- The whole form was extracted to `components/forms/NewRequestForm.tsx`
  (props: `onSuccess`/`onCancel`; resets itself after submit).
- `/merchandiser` renders it in a collapsible "New Supplier Advance Payment
  Request" card at the top of the queue; the "New Request" button toggles it.
- `/merchandiser/new` is now a redirect to `/merchandiser?new=1`, which
  auto-expands the section — bookmarks survive.
- The "No requests yet" empty state no longer references the retired public
  form.

### 3.3 Conditional tranche edit + add/delete (client choices: "any accounts
write" definition; delete allowed)
- `tranche_service.accounts_touched_reason(request_id)` — a human-readable
  reason if Accounts wrote anything: a paid tranche, an uploaded TT copy, a
  `payment_details` row (incl. partial ship-date/TT rows), or a **COMPLETED**
  invoice adjustment touching the request's tranches (pending
  merchandiser-raised adjustments don't count). `None` = untouched.
- `_assert_merchandiser_may_modify` — merchandiser tranche changes require
  status ∈ {pending_payment, pending_hom_approval} AND untouched. Applied to
  `update_tranche` and the two new operations. **Super Admin is exempt** and
  keeps the broader pre-existing rules (lock/terminal/paid checks).
  Behavior change: merchandisers can no longer edit tranches on held
  requests (previously possible).
- **New:** `add_tranche` (next tranche number, invoice-total ceiling, audit
  create row, deposit_amount re-derived) and `delete_tranche` (unpaid only,
  ≥1 tranche must remain, refuses tranches referenced by invoice adjustments
  — FK safety, audit delete row, totals re-derived; returns the label for the
  notification).
- **Endpoints:** `POST /requests/{id}/tranches`,
  `DELETE /requests/{id}/tranches/{tranche_id}`,
  `GET /requests/{id}/tranches/modifiable` → `{modifiable, reason}` so the UI
  mirrors the server rule instead of re-deriving it.
- **Notification:** adds reuse `notify_tranche_updated` ("added with amount
  …"); deletes use a new `notify_tranche_removed(request_id, label)` (the row
  is gone, so the label travels as an argument) — both fan out to Accounts.
- **Frontend:** `TrancheList` gains `canModify`/`modifyBlockedReason` props —
  edit/delete buttons and an inline "New Tranche" mini-form (amount + date,
  date defaults to today) appear only while modifiable; otherwise an amber
  note shows the exact reason. `merchandiser/[id]` feeds it from
  `useTranchesModifiable`.

**Tests** (12 new in `test_tranche_service.py`): edit blocked by payment row /
sibling TT / non-pending status; super-admin exemption; add numbering +
totals sync + ceiling + blocked-after-touch; delete totals sync +
last-tranche refusal + blocked-after-touch; non-owner add/delete forbidden;
untouched reason is None.

---

## Phase 4 — TT / payment processing rework · DONE (1 Aug 2026) · **migration 0022**

**Deliberately reverses July's C6 auto-pay.** Confirmed flow: per tranche,
the TT copy AND payment details are both mandatory, and only an explicit
"Mark Paid" click changes the status.

**Migration 0022** (`0022_tranche_payment_details.py`) — nullable
`payment_date` (date), `bank`, `payment_reference_number` (varchar 200) on
`payment_tranches`; clean `downgrade()`. Columns mirrored on the ORM model,
`TrancheResponse`, and the frontend `PaymentTranche` type.

**Backend** (`tranche_service.py`)
- `attach_tt_copy` — attach only, no status change; returns the tranche
  (tuple signature gone). Duplicate/replace rules unchanged.
- `pay_tranche` — readiness gate replaces the TT-only guard: missing TT copy /
  payment date / bank are all named in one 409 ("…cannot be marked paid until
  its TT copy and payment date and bank are recorded"). Reference number is
  NOT required. Final-tranche completion/lock logic unchanged.
- New `update_payment_details` — accounts-only, unpaid tranches only (paid =
  immutable), per-field audit rows, staged saves allowed
  (`TranchePaymentDetailsUpdate`, all fields optional).
- `accounts_touched_reason` extended: recorded tranche payment details now
  also freeze merchandiser tranche changes (Phase 3 guard).
- **Endpoints:** `POST /tranches/{id}/pay` re-introduced (was deleted in
  July's C6) — now readiness-gated, notifies `tranche_paid`;
  `PATCH /tranches/{id}/payment-details`; the tt-copy endpoint now always
  notifies `tranche_tt_attached` (never "paid").

**Reference number optional** (item 3.2) — request-level too:
`PaymentCreate.payment_reference_number` back to optional,
`process_payment`'s completeness gate drops it (Payment Date / Bank / Status
remain), `PaymentForm` zod + label updated.

**Frontend** (`TrancheList.tsx`, accounts mode) — per unpaid tranche:
a payment-details mini-form (date* / bank* / optional ref, per-tranche draft
state, staged saves), a plain "Upload TT Copy" button (upload toast no longer
claims payment), a readiness checklist (✓ TT copy uploaded · ✓ Payment
details recorded), and a **Mark {label} Paid** button that stays disabled
until both are green, behind a confirm dialog. `usePayTranche` +
`useUpdateTranchePaymentDetails` hooks; service methods restored/added.
The legacy paid-without-TT remediation block is untouched.

**Tests** (206 total after phase; 5 new, several reworked) —
`test_tt_upload_on_unpaid_tranche_auto_pays` is retired and REPLACED by
`test_tt_upload_no_longer_auto_pays` (documented as a deliberate reversal);
pay-path tests moved to a `_payable()` helper (TT + details, no reference);
new: pay-without-details rejected, reference-not-required, details
save+audit, details locked once paid, merchandiser cannot record details,
tranche details count as accounts-touch. `test_payment_integrity.py`: the
missing-field parametrize and `PaymentCreate` tests drop the reference
number.

---

## Phase 5 — Notification audit & missing triggers · DONE (1 Aug 2026)

**Audit deliverable:** [NOTIFICATION-MATRIX.md](NOTIFICATION-MATRIX.md) — the
full map of every state change, its recipients, trigger point, and the
deliberate non-triggers (admin roles excluded from fan-outs, payment-detail
saves, ship-date recording, soft-delete).

**Gaps found and filled** (all in `notification_service.py`, wired via
`BackgroundTasks` in `api/v1/requests.py`):

1. `notify_request_created(request_id)` — dispatches on the request's status:
   `pending_payment` → all active Accounts users (`request_created`, deep-link
   `/accounts/{id}`); `pending_hom_approval` → all active Head of Merchandiser
   users (`request_pending_hom`, deep-link `/hom/{id}`, "flagged supplier
   awaits approval"). Wired into `POST /requests` AND `hom-approve` (approval
   drops the request into the payment queue — Accounts now hear about it the
   same way as direct submissions).
2. `notify_status_change(request_id, new_status, actor_role, remarks)` —
   hold / resume / cancel / reopen previously emitted **nothing**
   (`transition_status` writes history + audit only). Routing: the actor's
   counterpart — merchandiser actions fan out to Accounts, accounts-side
   actions go to the raising merchandiser (via `_find_target_user`, so legacy
   public-form rows resolve too). Remarks appended when present. Wired into
   all four endpoints; resume disambiguates by actor role.
3. New shared internals `_active_users_with_role` / `_deliver_to_users`
   (bell rows + pushes for a recipient list) — used by the new entry points;
   pre-existing fan-outs left untouched to minimise risk.

**Tests** — `test_status_notifications.py` (8): builder routing/wording;
created-pending → both accounts users (HoM silent); flagged → HoM user only
(accounts silent); merch hold fan-out with remarks; accounts cancel → the
raising merchandiser with remarks + deep-link; reopen → merchandiser.

---

## Phase 6 — Accounts view: Cost of Fund + HoM remarks · DONE (1 Aug 2026)

Frontend-only, both on `accounts/[id]`.

**Cost of Fund during processing (item 3.4)** — finding: an fv-gated
Analytics Snapshot card already showed CoF on this page, so the gap was
placement, not data. Added a compact CoF strip **inside the Payment Details
card** (the processing surface): amount in the request currency plus accrual
context ("Accrues past Grace ETD {date} — {n}d overdue"), em-dash when the
snapshot hasn't computed one. Same `fv.cost_of_fund` field-visibility gate as
the snapshot card. No backend change — `analytics_snapshot` was already on
the detail response.

**HoM approval/rejection remarks (item 3.5)** — a "Head of Merchandiser
Decision — Approved/Rejected ({date})" block styled exactly like the
Merchandiser Remarks block above it, derived from `status_history` (latest
transition out of `pending_hom_approval`; `rejected_by_hom` = rejected,
anything else = approved). Requests that never went through HoM show
nothing; a decision without remarks shows "No reason recorded." (possible
only for pre-July decisions — remarks have been mandatory since C3).
Interpretation note: "render in the Accounts Payment Queue similar to
Merchandiser remarks" — merchandiser remarks render on the accounts DETAIL
page, so the HoM block does too; the queue list payload carries no
status_history and no list-level indicator was added.

---

## Phase 7 — Dashboards & analytics · DONE (1 Aug 2026)

### 4.1 Weekly Deposit Tracker (client choice: ETD-week buckets)
- `AnalyticsService.get_weekly_deposit_tracker()` — row-level unpaid
  ("requested") tranches on live requests, sorted by Estimated ETD (nulls
  last, portable ordering), bucketed into Monday–Sunday ISO weeks of the
  **ETD**; requests without an ETD trail in a "No ETD recorded" bucket. Each
  group carries per-currency outstanding totals.
- `GET /analytics/weekly-deposits` — gated by the existing
  `outstanding_tracker` section permission (same data domain, no new
  permission seeding needed).
- New **"Weekly Tracker"** tab beside "Outstanding" on `/analytics`
  (same permKey, so it appears for exactly the same audience): one card per
  week — header shows the week range + per-currency totals; rows show
  Request #, Invoice #, Supplier, Tranche, Unpaid Amount, Tentative Payment,
  Estimated ETD.

### 4.2 Analytical Snapshot → ALL shipments (client choice: both ID columns)
- `AnalyticsService.get_shipments_list()` — every live (non-cancelled/
  rejected/deleted) request with **Days Delayed computed server-side against
  today**: `max(0, today − estimated_etd)`, null when no ETD — so the number
  can never drift from the backend clock or the CoF logic's calendar.
  Sorted most-delayed first; ETD-less rows trail.
- `GET /analytics/shipments` — explicit role gate: head_of_merchandiser,
  accounts_team, super_admin, finance_admin.
- Shared `components/analytics/ShipmentsTable.tsx` — "Analytical Snapshot —
  All Shipments (N)" card, mounted on BOTH the HoM dashboard (above NPA) and
  the Accounts dashboard (below the queue tabs). Columns: **Request # AND
  Invoice #** (client decision — both, never ambiguous), Supplier, Amount,
  Original ETD, Days Delayed (green "On time" at 0, amber <7d, red ≥7d),
  Status. Client-side pagination, 25/page; rows deep-link to the role's own
  detail view.

**Tests** — `test_weekly_and_shipments.py` (4): ETD-week bucketing order +
labels + totals + trailing No-ETD bucket; paid/cancelled exclusion;
days-delayed maths (10d, 3d, floored future ETD, null) with most-delayed
ordering; identifiers present + rejected requests excluded.

---

# Batch complete — 1 Aug 2026

All seven phases delivered (Ship Date removal deliberately deferred by the
client). Final state: 218 backend unit tests green, `npx tsc --noEmit`
clean, migration head **0022**. Everything is uncommitted in the working
tree alongside the July change-note work.

Deploy checklist:
1. `alembic upgrade head` (applies 0020 → 0022; the inspected DB was at 0019).
2. Post-deploy: unpaid tranches with a July-era TT copy need their per-tranche
   payment details backfilled by Accounts before they can be marked paid
   (deliberate — no auto-migration of attestation data).
3. Announce: public form retired (shared links show a sign-in notice),
   TT upload no longer auto-pays, reference numbers optional again.

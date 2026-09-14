# Claude Code Prompt — Process Change Note (14 July 2026)

> Paste everything below the line into Claude Code from the repo root (`D:\Uma Apps\finance-operations`).

---

You are working in the **Advance Deposit Tracker (ADT)** monorepo: FastAPI + SQLAlchemy 2.x async + Alembic in `backend/`, Next.js 15 App Router + TanStack Query + Tailwind/ShadCN in `frontend/`.

Implement the changes from the 14 July 2026 Process Change Note. The full verified analysis is in `docs/change-note-14jul2026/CHANGE-LIST.md` — **read it first**; it contains exact file paths, line numbers, root causes and traps that I do not want you to rediscover.

## Ground rules

1. **Never edit `hf_space/`.** It is a stale fork of an older backend that lacks tranches and adjustments entirely. Backend changes go in `backend/` only.
2. **Status rules live in three places** — `backend/app/models/enums.py`, `backend/app/domain/rules/status_transitions.py`, and the Postgres trigger `enforce_status_transition()` from `migrations/versions/0012_fix_status_transition_trigger.py`. Adding a status or transition requires a migration too. None of the phases below should need a new status, but check before assuming.
3. **`deposit_amount` is derived.** It is kept in sync as the sum of tranches by `TrancheService._sync_request_totals`. Never write it directly.
4. Migration head is currently **0020**. New migrations continue from there, one per phase that needs one, with a working `downgrade()`.
5. Run `cd backend && pytest tests/unit -q` after every phase. Run `cd frontend && npx tsc --noEmit` after every frontend phase.
6. Work **one phase at a time**. After each phase, stop and give me a summary: files changed, tests added, anything you had to decide. Do not start the next phase until I confirm.
7. If a phase's acceptance criteria can't be met without a decision I didn't specify, stop and ask rather than guessing.

---

## Phase 1 — Frontend polish (no backend, no migration)

### 1a. Tranche tentative payment date defaults to today
Seed today's date in all four places: `frontend/src/app/(dashboard)/merchandiser/new/page.tsx:87` and `:328`, `frontend/src/app/form/page.tsx:146` and `:528`.

Use a shared helper (add to `frontend/src/lib/utils.ts`) that builds a **local-timezone** `YYYY-MM-DD` string. Do **not** use `new Date().toISOString().slice(0,10)` — for negative UTC offsets that returns yesterday. Add the `required` marker to both date `Field`s.

Do **not** touch `payment_tranches.tentative_payment_date` nullability — legacy rows are NULL by design.

### 1b. Show the deposit currency on tranche amount inputs
There is no per-tranche currency column and there should not be one. Just make the currency visible at entry: label the input `Amount ({currency})` or add a prefix adornment, in `merchandiser/new/page.tsx:275`, `form/page.tsx:479`, `components/tranches/TrancheList.tsx:152`.

Replace the `|| "USD"` fallbacks (`merchandiser/new/page.tsx:284, 333, 343`) by disabling the tranche block until a currency is selected. Reuse the existing `CNY → "CNY (RMB)"` label helper at `form/page.tsx:60` — promote it to `lib/utils.ts` and use it everywhere a currency code is displayed to a user, including `analytics/page.tsx:775`.

### 1c. Flagged-supplier submission message
`merchandiser/new/page.tsx:117-126` discards the create result and always toasts `"Request submitted successfully."` Capture the returned request and branch:

- `current_status === "pending_hom_approval"` → "Request sent to the Head of Merchandiser for approval."
- otherwise → "Request submitted."

Normalise "Head of Merchandis**ing**" → "Head of Merchandis**er**" in `components/forms/SupplierDefaultAlert.tsx:34` and `merchandiser/new/page.tsx:146` to match `ROLE_LABELS.head_of_merchandiser` (`lib/utils.ts:99`).

### 1d. One consistent request-ID nomenclature
`lib/utils.ts:43-51` currently returns `sunshine_invoice_number || request_number`, so "Request #" columns show `AGV-0003` instead of `Dep-2026-0004`.

Change `requestDisplayNumber` to return `req.request_number`. Then add a **separate** "Invoice #" column (table) or line (mobile card) showing `sunshine_invoice_number` (em-dash when null) to each of these five surfaces so the client-facing number is still available:

- `app/(dashboard)/hom/page.tsx:71` (header `:222`)
- `components/tables/RequestsTable.tsx:62, 84` (header `:46`)
- `app/(dashboard)/accounts/page.tsx` — Pending `:85, 124`, On Hold `:160, 194`, All `:224, 258`
- `app/(dashboard)/admin/page.tsx:58` (header `:130`)

Keep header/cell counts in sync. `requestMatchesSearch` (`utils.ts:55-73`) already searches all three fields — leave it alone. Backend notifications, emails and report exports already use `request_number` — do not change them.

**Acceptance:** create a request, let Accounts set a Sunshine invoice number, confirm every "Request #" column shows `Dep-YYYY-NNNN` and the invoice number appears in its own column. `npx tsc --noEmit` clean.

---

## Phase 2 — HOM decision path

### 2a. Reason mandatory on approve and reject
Add a **new** schema in `backend/app/schemas/deposit_request.py`:

```python
class HomDecisionRequest(BaseModel):
    remarks: str = Field(min_length=1, description="Reason is mandatory for HoM approval and rejection.")
```

Do **not** tighten `StatusChangeRequest` (`:77-78`) — it is shared by hold/resume/cancel/reopen/remarks. Use `HomDecisionRequest` on `hom_approve` (`api/v1/requests.py:313-332`) and `hom_reject` (`:335-354`).

Frontend:
- Approve currently has **no** remarks UI. Add a required textarea to the approve flow in both `app/(dashboard)/hom/page.tsx:151-159` and `hom/[id]/page.tsx:63-70`.
- Reject's textarea says "Reason for rejection (optional)" — drop "(optional)", mark required, and disable Confirm while `remarks.trim() === ""` (`hom/page.tsx:40-49`, `hom/[id]/page.tsx:33-42`).
- Make `remarks` non-optional in `useHomApprove`/`useHomReject` (`hooks/useRequests.ts:326-349`) and `requestService.homApprove`/`homReject` (`services/requestService.ts:155-161`).

### 2b. Push notification to the merchandiser on HOM rejection
`transition_status` emits no notifications at all, and `hom_reject` doesn't take `BackgroundTasks`. Web Push plumbing is working (`_push_to_user` → `pywebpush`/VAPID) — only the trigger is missing.

In `backend/app/services/notification_service.py`:
- Add `TYPE_HOM_REJECTED = "hom_rejected"` and `TYPE_HOM_APPROVED = "hom_approved"` alongside `:51-55`.
- Add a message builder beside `build_tranche_notification_message` (`:99-108`). Include the request number and the reason. Deep-link to `/merchandiser/{request_id}`.
- Add `notify_hom_decision(request_id, decision, remarks)`, resolving the recipient via the existing `_find_target_user` (it already handles both `created_by` and public-form `submitter_email`).

In `api/v1/requests.py`, add `background_tasks: BackgroundTasks` to both HOM endpoints and `background_tasks.add_task(...)` after a successful transition. Follow the existing pattern at `api/v1/tranches.py:98`.

**Acceptance:** unit tests that (i) an empty/missing `remarks` returns 422 on both endpoints, (ii) rejection creates a `Notification` row for the raising merchandiser containing the reason. No migration.

---

## Phase 3 — Payment integrity

Do **3a before 3b** — 3a is the enforcement point.

### 3a. A tranche cannot be marked paid without a TT copy

**Read the trap first.** `tranche_service.attach_tt_copy` (`:205-258`) is the *legitimate* auto-pay path, and it calls `pay_tranche` **before** writing `tt_copy_url` (`:239-251`). A naive guard breaks the only compliant flow. Extract a private `_mark_paid()` used by both, or reorder so the `tt_copy_*` fields are written first.

1. In `pay_tranche` (`:127-203`), after the already-paid check at `:151-152`, reject when `tranche.tt_copy_url` is falsy with a clear message: `"{label} cannot be marked paid until its TT copy is uploaded."`
2. Close the legacy bypass in `payment_service.process_payment` (`:69-148`). Today it requires only that a `payment_details` row exists (`:93-95`) and then bulk-marks **every** unpaid tranche PAID (`:101-124`). Remove the auto-pay loop and reject when unpaid tranches remain. `POST /requests/{id}/payment/process` is live even though the UI hides its button in tranche mode.
3. Consider deleting `POST /requests/{id}/tranches/{tranche_id}/pay` (`api/v1/tranches.py:102-122`) — with the guard in place, TT upload is the only route to PAID, so the endpoint is dead weight and a re-regression risk. Flag this to me rather than deciding alone.
4. Frontend `components/tranches/TrancheList.tsx`: delete the standalone Mark-Paid button (`:235-243`), its `ConfirmDialog` (`:289-296`), `doPay` (`:77-87`), the `payConfirmId` state (`:44`), and the `usePayTranche` import/call (`:8, 38`). Relabel the upload button (`:244-260`) to **"Upload TT Copy & Mark Paid"**. Keep the "paid but no TT copy yet" block (`:263-283`) for pre-gate legacy rows, but retitle it so it reads as legacy remediation.
5. Update the tests that currently call `pay_tranche` on TT-less tranches: `backend/tests/unit/test_tranche_service.py:100-107, 137-149, 151-162, 164-172, 174-179, 181-189`. **`test_tt_upload_on_unpaid_tranche_auto_pays` (`:193`) must keep passing** — it is what catches the ordering trap. Add a new test asserting `pay_tranche` without a TT copy raises.

No migration. No analytics impact — `get_outstanding_tracker` keys off `TrancheStatus.UNPAID`, so gating just keeps tranches outstanding longer, which is intended.

### 3b. Payment Details fields mandatory
Required: **Payment Date, Bank, Payment Reference Number, Payment Status.**

Frontend `components/forms/PaymentForm.tsx`:
- Make all four required in the zod schema (`:23-32`) and remove the empty `<option value="">— Select status —</option>` (`:165`). Add `required` to the four `Field`s (`:139-169`).
- **Fix a hidden bug:** `useForm` (`:101-105`) destructures only `isSubmitting`, so zod messages never render. Add `formState: { errors, isSubmitting }` and pass `error={errors.x?.message}` to each Field.
- Check the force-sync `values:` prop (`:107-113`) doesn't re-trip validation every render on legacy rows with NULL columns.

Backend:
- `PaymentCreate` and `PaymentUpdate` are the same class (`schemas/payment.py:12-23`) and back both POST and PATCH. Keep `PaymentUpdate` permissive so partial PATCH still works; require the four on `PaymentCreate`.
- Add a completeness gate in `payment_service.process_payment` after `:95` rejecting when any of the four is NULL.
- `set_ship_date` (`:197-239`) and `attach_tt_copy` (`:150-195`) must stay exempt — they legitimately create partial `payment_details` rows post-lock. Leave `ShipDateUpdate` (`schemas/payment.py:26-27`) alone.
- **No DB `NOT NULL`** on these columns — it would immediately break `set_ship_date` and `attach_tt_copy`. Enforce at schema + service layer only.

**Acceptance:** cannot mark a tranche paid without uploading a TT copy, from UI *or* raw API; TT upload still auto-pays; `process_payment` refuses incomplete payment details; full unit suite green.

---

## Phase 4 — Remove the Estimated Shipment Date section

**Field being removed: `deposit_requests.estimated_shipment_date`.** Verified: it has **zero** analytics consumers. Grace ETD, `payment_to_ship_days`, `actual_etd_overdue_days` and Cost of Fund all derive from `estimated_etd` and `payment_details.ship_date`. Reports use those two as well.

**Do not touch** `payment_details.ship_date`, `POST /requests/{id}/payment/ship-date`, or the Ship Date block in `PaymentForm.tsx:183-207`. Different field, and Phase 5 depends on it.

**Before writing the migration:** `0001_initial_schema.py:177` declares this column `DATE NOT NULL` and no later migration relaxes it, yet `models/deposit_request.py:42` says `nullable=True` and both create forms omit the field. Report the live schema state to me before proceeding.

Remove, in this order:

*Frontend* — `app/(dashboard)/accounts/[id]/page.tsx:67-80` and `:210-236` · `components/tables/RequestsTable.tsx:51` **and** `:73-75` (header and cell together) · `app/(dashboard)/accounts/page.tsx:112` **and** `:129` · `app/(dashboard)/merchandiser/[id]/page.tsx:167` · `types/index.ts:179` · `services/requestService.ts:36` · `app/(dashboard)/admin/form-config/page.tsx:36` and its entry in the default `required` list at `:43`.

*Backend* — `schemas/deposit_request.py:29, 71, 114` · `api/v1/public_form.py:140, 211` · **`services/bi_service.py:71`** (the text-to-SQL prompt schema — miss this and BI chat generates SQL against a dropped column) · `backend/scripts/migrate_csv.py:334` (leave `:292, 373, 382`, those are `ship_date`) · `models/deposit_request.py:42`.

*Migration* — **stage it.** Migration A: `ALTER TABLE deposit_requests ALTER COLUMN estimated_shipment_date DROP NOT NULL` (harmless if already nullable). Ship that with the code removal. Migration B, as a separate follow-up once A is deployed and `bi_service.py` is updated: `DROP COLUMN`. `downgrade()` can only re-add it as nullable — say so in the docstring.

**Acceptance:** grep for `estimated_shipment_date` returns only migration files; analytics summary, shipment KPIs, delay buckets and CoF all still return identical numbers before and after; `npx tsc --noEmit` clean.

---

## Phase 5 — Exclude shipped requests from Adjust Invoice

Rule: once the shipment date is updated, that Advance Payment Request is no longer available in the Adjust Invoice function.

"Shipment date updated" = **`payment_details.ship_date IS NOT NULL`** (not `estimated_etd`, and not the field Phase 4 deleted).

1. In `adjustment_service.supplier_tranche_options`, exclude requests with a non-null `payment_details.ship_date` from **both** the paid-source and unpaid-destination lists.
2. Re-assert the same rule inside `adjustment_service.create` so the API can't be driven around the UI. Raise a clear business-rule error naming the request.
3. In `app/(dashboard)/adjust-invoices/page.tsx`, show why options are unavailable rather than silently returning an empty list — e.g. an inline note on the supplier picker.

**Acceptance:** unit test — a paid tranche on a request with `ship_date` set appears in neither list, and a direct `POST /adjustments` referencing it is rejected.

---

## Phase 6 — Adjust Invoices: merchandiser requests + Accounts queue

Largest item. Read §B3 of `CHANGE-LIST.md` before starting, and **confirm scope with me first** — §9 of the note still lists adjustment approval as an open item while the red page-3 text describes an Accounts queue.

Current state: merchandisers cannot create, view, or navigate to the module; adjustments are created terminal-`COMPLETED` (`adjustment_service.py:100`); there is no pending list and no approve/reject endpoint.

**No migration needed for the statuses** — `AdjustmentStatus.PENDING_APPROVAL` and `REJECTED` already exist in the enum and the Postgres `adjustment_status` type (migration 0018), reserved for exactly this (`enums.py:90-97`).

1. **Roles.** Add `merchandiser` as a *requester* (can raise and view own), keeping `accounts_team`/`super_admin` as deciders. Update all four gates: `adjustment_service.py:38`, `api/v1/adjustments.py:21-22`, `app/(dashboard)/adjust-invoices/page.tsx:41, 116`, `components/layout/Sidebar.tsx:39`.
2. **Status on create.** Merchandiser-raised → `PENDING_APPROVAL`. Accounts/super-admin-raised → `COMPLETED` (unchanged).
3. **Balance safety — critical.** `PENDING_APPROVAL` rows must **not** consume paid-tranche balance in `supplier_tranche_options` or in the create-time validation until approved. Add a test for double-spend across two pending requests against the same paid tranche.
4. **Reason required.** `AdjustmentCreate.reason` is `str | None = None` (`schemas/tranche.py:79-83`) and the UI says "Reason (optional)" (`adjust-invoices/page.tsx:219`). Make it mandatory for merchandiser-raised requests, and mandatory on reject.
5. **Endpoints.** `GET /adjustments/pending`, `POST /adjustments/{id}/approve`, `POST /adjustments/{id}/reject`. Expose `status` on `AdjustmentResponse`. Apply the Phase 5 `ship_date` exclusion at approve time too — state may have changed since the request was raised.
6. **Notifications.** `adjustment_requested` → all active `accounts_team` users, fanning out exactly like `notify_tranche_updated` (`notification_service.py:393-413`). `adjustment_decided` → back to the raising merchandiser, including the reason. Wire `BackgroundTasks` into create, approve and reject (`api/v1/adjustments.py` currently imports nothing from `notification_service`).
7. **UI.** Add an "Accounts Queue" card above Adjustment History in `adjust-invoices/page.tsx` with Approve/Reject actions and a mandatory-reason dialog on reject. Add a `status` column to the History table (`:256-265`).
8. **Audit.** `adjustment_service.create` already writes three audit rows (`:106-133`) — extend the same pattern to approve and reject so §8 of the note (audit visible at request level *and* in the module) holds.

**Acceptance:** merchandiser raises an adjustment → lands in the Accounts queue as pending → Accounts receives a push → Accounts approves with a reason → merchandiser receives a push → balances update only on approval → every step appears in both the request-level audit trail and the module.

---

## Deliverable at the end

A short `docs/change-note-14jul2026/IMPLEMENTED.md` mapping each change-list ID (A1, A2, B1–B3, C1–C7) to the commits/files that satisfied it, plus anything deferred and why.

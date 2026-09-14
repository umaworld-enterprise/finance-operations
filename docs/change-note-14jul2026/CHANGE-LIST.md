# Change List — Process Change Note (14 July 2026)

Source: `Sunshine_Deposit_Tracker_Process_Change_Note.pdf`
Scope: **red-font text only**, plus the three annotated screenshots (pages 5–6, and `tmp/pdf-review/change-note-5.png` / `-6.png`).
Each item below was verified against the working tree before being listed.

Legend — **GAP** = must be built · **PARTIAL** = exists but doesn't meet the note · **DONE** = already satisfied, no work needed.

---

## A. Red font, page 2 (§4 tranche table)

### A1 — Tentative payment date must default to today's date · **PARTIAL**
Red text: *"Yes (default today date)"*

Field is already mandatory (`TrancheCreate.tentative_payment_date: date`, zod `.min(1)`), but every form seeds it blank.

| File | Line | Current |
|---|---|---|
| `frontend/src/app/(dashboard)/merchandiser/new/page.tsx` | 87 | `tentative_payment_date: ""` (defaultValues) |
| same | 328 | `append({ … tentative_payment_date: "" })` |
| `frontend/src/app/form/page.tsx` | 146 | `tentative_payment_date: ""` |
| same | 528 | `appendTranche({ … tentative_payment_date: "" })` |

**Do:** seed all four with a local-timezone `YYYY-MM-DD` today string. Add the `required` marker to the date `Field` so the asterisk shows.
**Do NOT:** use `new Date().toISOString()` (UTC shift picks yesterday for negative offsets), and do NOT make `payment_tranches.tentative_payment_date` `NOT NULL` — legacy rows are NULL by design (migration 0018, `deposit_request_service.py:184`). No migration needed.

### A2 — Tranche amount is entered "in the deposit currency" (yellow highlight) · **PARTIAL**
Structurally already true — currency lives once on the request, there is no per-tranche currency column, so a tranche amount can only ever be in the request currency. What's missing is that the entry rows never show which currency.

**Do:** label the per-tranche amount input `Amount ({currency})` or add a currency prefix in `merchandiser/new/page.tsx:275`, `form/page.tsx:479`, `components/tranches/TrancheList.tsx:152`. Replace the misleading `|| "USD"` fallback (`merchandiser/new/page.tsx:284,333,343`) by disabling the tranche block until a currency is chosen. Reuse the existing `CNY → "CNY (RMB)"` label helper (`form/page.tsx:60`).

### A3 — Merchandiser tranche edit pushes to Accounts Team (yellow highlight) · **DONE**
`api/v1/tranches.py:98` → `notify_tranche_updated` (`notification_service.py:374-419`) fans out to every active `accounts_team` user with a real Web Push. No change required. (Minor, optional: `super_admin`/`finance_admin` are not notified.)

---

## B. Red font, pages 2–3 (§7 Adjust Invoices)

### B1 — Once the Shipment date is updated, that request must be excluded from Adjust Invoice · **GAP**
Red text, page 2.

Today `GET /adjustments/supplier/{supplier_id}/options` (`api/v1/adjustments.py:63`, `adjustment_service.supplier_tranche_options`) returns every paid tranche as a source and every unpaid tranche as a destination, with no shipment filter.

**Important disambiguation** — there are three date fields and this rule keys off the third:

| Field | Table | Set by |
|---|---|---|
| `estimated_shipment_date` | `deposit_requests` | the section item **C5 deletes** |
| `estimated_etd` | `deposit_requests` | merchandiser at creation — drives all analytics |
| `ship_date` | `payment_details` | Accounts, via `POST /requests/{id}/payment/ship-date` |

"Shipment date updated" = **`payment_details.ship_date IS NOT NULL`**. So C5 and B1 do not conflict.

**Do:** exclude any request whose `payment_details.ship_date` is set from both the source and destination lists, and re-assert the same rule server-side in `adjustment_service.create` (so the API can't be driven around the UI). Surface the reason in the UI when a request disappears.

### B2 — Any Adjust Invoice change pushes a notification to the Accounts Team · **GAP**
Red text, page 3. Zero notifications exist on this path — `adjustment_service.py:48-134` writes the adjustment plus three audit rows and returns; `api/v1/adjustments.py` has no `BackgroundTasks` parameter and imports nothing from `notification_service`.

**Do:** add an `adjustment_requested` / `adjustment_recorded` notification type, fan out to active `accounts_team` users mirroring `notify_tranche_updated`, and wire `BackgroundTasks` into the create endpoint.

### B3 — A queue in the Adjust Invoice module for merchandiser-submitted adjustment requests, so Accounts can act on them · **GAP (largest item in the note)**
Red text, page 3. This is entirely net-new, and it contradicts the current permission model:

- Merchandisers **cannot create, view, or navigate to** the module. Write roles are `{accounts_team, super_admin}` in three places — `adjustment_service.py:38`, `api/v1/adjustments.py:22`, `adjust-invoices/page.tsx:41`. View roles add only `finance_admin` (`Sidebar.tsx:39`).
- Adjustments are created terminal-complete — `adjustment_service.py:100` `status=AdjustmentStatus.COMPLETED`.
- No pending list endpoint, no approve/reject endpoint. The page has exactly two cards: New Adjustment form and read-only Adjustment History.

**Good news:** no migration is needed for the status states — `AdjustmentStatus.PENDING_APPROVAL` and `REJECTED` already exist in the enum and the PG type (migration 0018), deliberately reserved for this (`enums.py:90-97`).

**Do:** grant merchandisers request-only access; create merchandiser-raised adjustments as `PENDING_APPROVAL` (Accounts-raised stay `COMPLETED`); add `GET /adjustments/pending` and `POST /adjustments/{id}/approve|reject` with a mandatory reason; add an "Accounts Queue" card above History; make `AdjustmentCreate.reason` required (`schemas/tranche.py:79` is currently `str | None = None`, UI labels it "Reason (optional)"); and — critical — make sure `PENDING_APPROVAL` rows do **not** consume paid-tranche balance in `supplier_tranche_options` until approved.

> §9 of the note lists "whether reallocation requires a separate approval step" as an open item. The red page-3 text answers it: yes, there is a queue Accounts acts on. Confirm this reading before building.

---

## C. Red font, pages 5–6 (numbered points 1–7)

### C1 (point 1) — Flagged supplier: the submission message must say the request went to the 'Head of Merchandiser'; otherwise plain "request submitted" · **PARTIAL**
Backend routing is correct (`deposit_request_service.py:48-64` sets `PENDING_HOM_APPROVAL` when the supplier is flagged and overridden) and the create response already carries `current_status`.

The gap is the toast. `merchandiser/new/page.tsx:117-126` discards the mutation result and always shows `"Request submitted successfully."`

**Do:** capture the created request and branch on `current_status === "pending_hom_approval"`. Also normalise the wording — the pre-submit banners say "Head of Merchandis**ing**" (`SupplierDefaultAlert.tsx:34`, `merchandiser/new/page.tsx:146`); the note and `ROLE_LABELS.head_of_merchandiser` (`lib/utils.ts:99`) both say "Head of Merchandiser".

### C2 (point 2) — Request ID must use one consistent nomenclature · **GAP** *(screenshot: HOM queue "Request #" column showing `AGV-0003`)*
Root cause is intentional and single-source — `lib/utils.ts:43-51`:

```ts
export function requestDisplayNumber(req) {
  return req.sunshine_invoice_number || req.request_number;   // ← AGV-0003 wins
}
```

So the Sunshine invoice number *replaces* the request number under a header that reads "Request #". Ten rendered positions across four call sites are affected:

| Surface | File:line |
|---|---|
| HOM approval queue | `hom/page.tsx:71` |
| Requests table (merchandiser history) | `components/tables/RequestsTable.tsx:62, 84` |
| Accounts — Pending / On Hold / All (table + mobile card each) | `accounts/page.tsx:85, 124, 160, 194, 224, 258` |
| Admin overview — recent requests | `admin/page.tsx:58` |

Everything else is already correct: all three detail pages, merchandiser activity, analytics, drill-down, charts, **all notifications** (`notification_service.py:71,75,100,112,116`), email, and **all report exports** (`report_service.py:86,141,182,222,253`) use `request_number`.

**Do:** make `requestDisplayNumber` return `req.request_number`, and add a separate "Invoice #" column/line to the five list surfaces so the Sunshine number stays visible. `requestMatchesSearch` (`utils.ts:55-73`) already searches all three fields, so search is unaffected.

### C3 (point 3) — HOM approve/reject: reason is mandatory · **PARTIAL**
- Backend: both endpoints accept `StatusChangeRequest` with `remarks: str | None = None` and no `min_length` (`schemas/deposit_request.py:77-78`, `api/v1/requests.py:313-354`).
- Frontend approve: **no remarks UI at all** (`hom/page.tsx:151-159`, `hom/[id]/page.tsx:63-70`).
- Frontend reject: textarea placeholder literally reads *"Reason for rejection (optional)"*; Confirm is never disabled, so an empty string submits.

**Do:** add a dedicated `HomDecisionRequest` with `remarks: str = Field(min_length=1)` for both endpoints — do **not** tighten the shared `StatusChangeRequest`, which is also used by hold/resume/cancel/reopen/remarks. Add a required remarks textarea to the approve flow, make reject's required, disable Confirm while blank, and drop `?` from `useHomApprove`/`useHomReject` and the two `requestService` methods.

### C4 (point 4) — HOM rejection pushes a notification to the merchandiser who raised the request · **GAP**
`transition_status` emits **zero** notifications (it writes `StatusHistory` + audit only), and `hom_reject` (`api/v1/requests.py:335-354`) doesn't even take `BackgroundTasks`. Existing notification types are limited to `payment_processed`, `tt_copy_attached`, `tranche_paid`, `tranche_tt_attached`, `tranche_updated` (`notification_service.py:51-55`).

Web Push itself is fully working (`_push_to_user` → `pywebpush`/VAPID, dead-endpoint pruning) — only the trigger is missing.

**Do:** add `hom_rejected` (and `hom_approved`), a `notify_hom_decision(request_id, decision, remarks)` entry point reusing `_find_target_user` (which correctly handles both `created_by` and public-form `submitter_email`), and wire `BackgroundTasks` into both HOM endpoints.

### C5 (point 5) — Remove the Estimated Shipment Date section · **GAP** *(screenshot: accounts request detail)*
The section is `accounts/[id]/page.tsx:210-236` (+ handler at 67-80), writing `deposit_requests.estimated_shipment_date` via the generic `PATCH /requests/{id}`.

**Verified safe:** `estimated_shipment_date` has **zero analytics consumers**. `analytics/engine.py` never references it — Grace ETD, `payment_to_ship_days`, `actual_etd_overdue_days` and Cost of Fund all derive from `estimated_etd` and `payment_details.ship_date`. Reports use `estimated_etd` and `ship_date` only. Removal cannot break shipment-KPIs, delay buckets or CoF.

Full cleanup list:

*Frontend* — `accounts/[id]/page.tsx:67-80, 210-236` · `RequestsTable.tsx:51` + `73-75` (header **and** cell, or column count drifts) · `accounts/page.tsx:112` + `129` · `merchandiser/[id]/page.tsx:167` · `types/index.ts:179` · `services/requestService.ts:36` · `admin/form-config/page.tsx:36` and `:43` (already-dead entry, still in the default *required* list).

*Backend* — `models/deposit_request.py:42` · `schemas/deposit_request.py:29, 71, 114` · `api/v1/public_form.py:140, 211` · **`services/bi_service.py:71`** (text-to-SQL prompt schema — if this isn't updated the BI chat will emit SQL against a dropped column) · `backend/scripts/migrate_csv.py:334`.

**Two things to watch:**
1. **Latent schema bug.** `0001_initial_schema.py:177` declares `estimated_shipment_date DATE NOT NULL` and no later migration relaxes it, yet the model says `nullable=True` and both create forms omit the field. ORM and DB disagree — confirm the live schema before writing the migration.
2. **Sequencing.** Ship the UI/schema removal plus `ALTER COLUMN … DROP NOT NULL` first; drop the column in a follow-up migration only after `bi_service.py:71` and `migrate_csv.py:334` are updated. `downgrade()` can only re-add it as nullable.

Do **not** touch `POST /requests/{id}/payment/ship-date` or the Ship Date block in `PaymentForm.tsx:183-207` — different field, and B1 depends on it.

### C6 (point 6) — A tranche must not be markable as paid without a TT copy upload · **GAP** *(screenshot: "Mark this tranche as paid?" dialog)*
Currently possible via **two** routes:

1. `tranche_service.pay_tranche()` (127-203) validates role, lock, already-paid and request status — **no `tt_copy_url` check**. Exposed at `POST /requests/{id}/tranches/{tranche_id}/pay`, driven by the bare "Mark {label} Paid" button (`TrancheList.tsx:235-243`) and the dialog at `:289-296`.
2. **Worse** — the legacy `payment_service.process_payment()` (69-148) requires only that a `payment_details` row exists, then **bulk-marks every unpaid tranche PAID** (lines 101-124). The UI hides the button in tranche mode but `POST /requests/{id}/payment/process` is live.

**Do:** add the `tt_copy_url` guard in `pay_tranche`; close the `process_payment` bypass; delete the standalone Mark-Paid button, its dialog, `doPay`, and the `usePayTranche` wiring, leaving `Upload TT Copy & Mark Paid` as the only path.

> **Ordering trap — do not skip.** `attach_tt_copy` (205-258) is the *legitimate* auto-pay path and it calls `pay_tranche` **before** writing `tt_copy_url` (246-251). Adding the guard naively breaks the only compliant flow. Fix by writing the `tt_copy_*` fields first, or extract a private `_mark_paid()`.

Tests that will need updating: `backend/tests/unit/test_tranche_service.py` lines 100-107, 137-149, 151-162, 164-172, 174-179, 181-189 all call `pay_tranche` on TT-less tranches. `test_tt_upload_on_unpaid_tranche_auto_pays` (line 193) must keep passing — it's what catches the ordering trap.

No migration. No analytics impact (`get_outstanding_tracker` keys off `TrancheStatus.UNPAID`, so gating just means tranches stay outstanding longer — intended).

### C7 (point 7) — Payment Details fields must be mandatory · **GAP** *(screenshot: Payment Date, Bank, Payment Reference Number, Payment Status)*
All four are optional at every layer: `PaymentForm.tsx:23-32` (all `.optional()`, no `required` props, `payment_status` even ships an empty `<option>` at :165), `schemas/payment.py:12-19` (all `| None = None`), `payment_service.create_or_update` (no field-presence validation), `models/payment.py:19-22` (all nullable), and `ck_payment_status` explicitly permits NULL.

**Do:**
- Frontend: require all four in the zod schema, drop the empty status option, add `required` markers. **Also fix a hidden bug** — `useForm` at `:101-105` destructures only `isSubmitting`, so zod messages are currently invisible; add `formState: { errors, isSubmitting }` and pass `error=` to each Field. And check the force-sync `values:` prop at `:107-113` doesn't re-trip validation on legacy NULL rows every render.
- Backend: keep `PaymentUpdate` permissive (it's the same class as `PaymentCreate` and backs `PATCH`), require the four on `PaymentCreate`, and add a completeness gate in `process_payment`. `set_ship_date` (197-239) and `attach_tt_copy` (150-195) must stay exempt — they legitimately create partial rows post-lock.
- **No DB `NOT NULL`.** Enforce at schema + service layer; a DB constraint would immediately break `set_ship_date` and `attach_tt_copy`.

---

## Not in the change list

**§10 Outstanding Deposit Tracker (pages 3–4) is black font, and is already built** — `GET /analytics/outstanding` + the "Outstanding" tab (`analytics/page.tsx:726-805`) already support weekly / merchandiser / customer / vertical grouping with dynamic per-currency columns, and are unit-tested (`test_outstanding_tracker.py`). Three cosmetic/latent points if you want them separately:

1. The note says "may be included in the Analysis tab where COF analysis is given" — it's currently a sibling tab, while Cost of Fund sits on Overview.
2. Column headers render the raw code `CNY`; the note writes "RMB". A display alias already exists at `form/page.tsx:60`.
3. **Latent data leak:** `get_outstanding_tracker` applies no `_merchandiser_scope` filter (unlike `get_summary` / `get_shipment_kpis`). Merchandisers aren't in the default permission list, but if an admin ever grants the section at runtime they'd see everyone's deposits.

---

## Suggested build order

| Phase | Items | Why here |
|---|---|---|
| 1 | A1, A2, C1, C2 | Frontend-only, zero risk, immediately visible |
| 2 | C3, C4 | HOM decision path — schema + notification type together |
| 3 | C6, C7 | Payment integrity. C6 first (it's the enforcement point), and mind the `attach_tt_copy` ordering trap |
| 4 | C5 | Field removal — staged: UI/schema + `DROP NOT NULL`, then drop the column |
| 5 | B1 | Depends on C5 being settled so `ship_date` vs `estimated_shipment_date` is unambiguous |
| 6 | B2, B3 | Largest item: new roles, new statuses, new endpoints, new UI |

## Open questions before starting

1. **B3 vs §9.** §9 still lists adjustment approval as an open item, but the red page-3 text describes an Accounts queue. Confirm merchandisers should be able to *raise* adjustment requests.
2. **C2.** Should the Sunshine invoice number stay visible as its own "Invoice #" column in the five list views, or be dropped from lists entirely?
3. **C5.** Confirm the production `deposit_requests.estimated_shipment_date` column really is nullable before the migration is written.
4. **C7.** Should `payment_status` default to `processed` rather than forcing an explicit pick?

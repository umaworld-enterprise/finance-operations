# Advance Deposit Tracker

Enterprise web application replacing the Google Form → Google Sheet → manual workflow for supplier advance deposits at Sunshine Finance & Operations.

**Status:** ✅ **Project completed 11 July 2026.** Kick-off meeting 18 June 2026, work started 19 June 2026, finished 11 July 2026 (44 production deploys · 22 change requests). Now in **live usage / maintenance** — awaiting any updates or user-suggested changes arising from real-world use.

**Stack:** Next.js 15 (App Router) · FastAPI · Supabase PostgreSQL · TanStack Query · Tailwind CSS · ShadCN UI · SQLAlchemy 2.x · Alembic

---

## Architecture Overview

```
Railway (Next.js frontend, PWA)
  └── REST/JSON → Railway (FastAPI backend, 2 uvicorn workers)
                    ├── Supabase PostgreSQL (+ Auth + RLS)
                    ├── Google Drive (TT copy uploads, service account)
                    └── Web Push (VAPID) + SMTP (optional)

Public form → /form/{slug} → /api/v1/public-form
```

- **5 Roles:** Super Admin · Finance Admin · Accounts Team · Merchandiser · Head of Merchandiser
- **Full status lifecycle:** pending_payment → hold / cancel / process / reopen (+ HoM approval gate)
- **Record locking** after payment_processed (Super Admin override only)
- **Defaulted supplier gate** blocks new requests at form submission
- **Payment notifications:** in-app bell + Web Push to the request's merchandiser when accounts processes a payment; the TT copy (bank document) is uploaded to Google Drive and its link travels with the notification. Optional email to HoM + super admins via SMTP.
- **Per-user accessibility:** font size (Default / Large / Extra Large) from the Settings page, persisted per account
- **Analytics engine** computes 5 metrics: Grace ETD, ETD Grace Overdue Days, Payment-to-Ship Days, Payment-to-Request Days, Cost of Fund
- **3 export formats:** Excel (openpyxl), CSV, PDF (ReportLab)
- **Supabase RLS** enforces role scoping at the database layer

---

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- A Supabase project (free tier works)

### 1. Clone & configure environment

```bash
git clone <repo>
cd "Advance Deposit Tracker"

# Backend
cp backend/.env.example backend/.env
# Fill in SUPABASE_URL, SUPABASE_JWT_SECRET, DATABASE_URL, GOOGLE_WEBHOOK_SECRET

# Frontend
cp frontend/.env.local.example frontend/.env.local
# Fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
```

### 2. Start the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run migrations (against Supabase or local postgres from docker-compose)
alembic upgrade head

# Seed master data
python scripts/seed.py

# Start dev server
uvicorn app.main:app --reload --port 8000
```

Or with Docker Compose (spins up FastAPI + local PostgreSQL):

```bash
docker compose up --build
```

### 3. Apply Supabase RLS policies

In the Supabase SQL editor, run the contents of:

```
supabase/rls_policies.sql
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 5. Run tests

```bash
cd backend
pytest tests/unit -v
```

---

## Deployment (Railway — current production)

Both services live in one Railway project. **Always deploy from inside the service subdirectory** — running `railway up` from the monorepo root fails Railpack detection.

### Backend

```bash
cd backend
railway up --service backend
```

`backend/railway.toml` builds the Dockerfile and starts with `alembic upgrade head && uvicorn ... --workers 2`, so **migrations apply automatically on every deploy**. Healthcheck: `/health`.

### Frontend

```bash
cd frontend
railway up --service frontend
```

`frontend/railway.toml` healthchecks **`/login`** — do not point it at `/`, which 307-redirects cookie-less probes to /login and fails Railway's 2xx requirement. `NEXT_PUBLIC_*` variables (including `NEXT_PUBLIC_VAPID_PUBLIC_KEY`) are inlined at **build time** — set them on the service *before* deploying.

---

## Supabase Setup

1. Create a new Supabase project.
2. Under **Settings → API**, copy:
   - `Project URL` → `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
   - `anon public` key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (backend only, never expose to client)
   - `JWT Secret` → `SUPABASE_JWT_SECRET`
3. Under **Authentication → Providers**, enable **Google** and add your OAuth credentials.
4. Set the redirect URL to `https://your-frontend.vercel.app/auth/callback`.
5. Run Alembic migrations against the Supabase connection string (use the **Transaction pooler** URL for serverless or the **Session pooler** URL for the Docker container).
6. Run `supabase/rls_policies.sql` in the SQL editor.

---

## Environment Variables Reference

| Variable | Where | Description |
|---|---|---|
| `SUPABASE_URL` | Backend | Supabase project URL |
| `SUPABASE_JWT_SECRET` | Backend | JWT secret from Supabase settings |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | Service role key for admin operations |
| `DATABASE_URL` | Backend | PostgreSQL connection string (asyncpg driver) |
| `GOOGLE_WEBHOOK_SECRET` | Backend | HMAC shared secret with Apps Script |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Backend | Service account JSON (single line) — used for Sheets sync AND Drive TT copy uploads |
| `GOOGLE_DRIVE_FOLDER_ID` | Backend | Shared Drive folder for TT copies (Shared Drive required — service accounts have zero My Drive quota). Shared with the SA email as Content Manager |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Backend | Web Push keys (`npx web-push generate-vapid-keys --json`). Empty → push off, bell still works |
| `VAPID_CLAIMS_EMAIL` | Backend | Contact email in VAPID claims |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | Backend | HoM/super-admin payment emails. Empty host → silently disabled |
| `CORS_ORIGINS` | Backend | JSON array of allowed origins |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend | Supabase anon key |
| `NEXT_PUBLIC_API_URL` | Frontend | FastAPI base URL |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | Frontend | Same value as backend `VAPID_PUBLIC_KEY`; **inlined at build time** |

---

## Project Structure

```
Advance Deposit Tracker/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/v1/             # Route handlers
│   │   ├── domain/rules/       # Status machine, lock rules, supplier gate
│   │   ├── services/           # Business logic
│   │   ├── repositories/       # Data access (SQLAlchemy async)
│   │   ├── models/             # ORM models
│   │   ├── analytics/          # Engine + snapshot job
│   │   ├── integrations/       # Google Drive (TT copies)
│   │   └── migrations/         # Alembic versions (head: 0016)
│   ├── tests/                  # Unit tests (SQLite in-memory)
│   ├── scripts/seed.py         # Master data seed
│   └── Dockerfile
├── frontend/                   # Next.js 15 application
│   └── src/
│       ├── app/(dashboard)/    # Role-scoped pages
│       ├── components/         # UI, forms, charts, tables
│       ├── hooks/              # TanStack Query hooks
│       ├── services/           # API call wrappers
│       └── types/              # TypeScript types
└── supabase/
    └── rls_policies.sql        # Supabase RLS policies
```

---

## Analytics Metrics

| Metric | Formula |
|---|---|
| Grace ETD | `estimated_etd + etd_grace_days` (from system_config) |
| ETD Grace Overdue Days | `max(0, ship_date_or_today - grace_etd)` |
| Payment-to-Ship Days | `ship_date - payment_date` |
| Payment-to-Request Days | `payment_date - created_at` |
| Actual ETD Overdue Days | `(ship_date or today) - estimated_etd`, **signed** (negative = shipped early), accruing day by day while unshipped |
| Cost of Fund | `deposit_amount × rate × actual_etd_overdue_days / 365` — **zero while within the 10-day grace**; once grace is exceeded the charge counts **retroactively from Est ETD** (day 1, not day 11); early shipment keeps the **negative** notional gain. Zero until a payment is recorded. (Client rule confirmed 2026-07-10 — deliberately diverges from their sheet for within-grace rows, which the sheet charges.) **Stops** the moment the actual ship date is recorded via `POST /requests/{id}/payment/ship-date` — writable on **locked** records by super_admin / finance_admin / accounts_team (audited; single write path — ship_date is no longer part of the payment PATCH payload) |

Rate (default **12%** p.a.) and grace days are configurable in the `system_config` table — no hardcoded values.

Default status thresholds: `on_time` · `delayed` (≤30 days overdue) · `critical` (>30 days).

**Display:** per-request Cost of Fund renders in the request's own currency (the snapshot payload carries `currency`); the "Total Cost of Fund" tiles sum across currencies and are indicative only — per-currency views (`get_overdue_by_currency`, delay buckets) are authoritative.

**Role scoping:** all analytics a merchandiser can reach — summary, per-request snapshots, monthly MoM/YTD trends, shipment KPIs — are filtered to their own requests via the shared `_merchandiser_scope()` predicate in `analytics_service.py` (created in-app OR public-form submission matching their registered email). The five section endpoints merchandisers cannot access (overdue-by-currency, delay-buckets, by-*) are protected by `_check_section_access` (403) but are NOT data-scoped — do not add `merchandiser` to those sections in Analytics Access without scoping them first.

---

## Payment Notifications & TT Copy

Flow (accounts side is deliberately process-first):

1. Accounts fills payment details and clicks **Process Payment & Lock**.
2. On the now-locked record, accounts uploads the bank's **TT copy** (PDF/JPG/PNG ≤ 10 MB) — `POST /requests/{id}/payment/tt-copy` is the **one deliberate exception to the record lock**: only the three `tt_copy_*` fields are writable through it, accounts/super-admin only, audit-logged.
3. The backend stores the file in the Google Drive Shared Drive (`GOOGLE_DRIVE_FOLDER_ID`) as `TT_{request_number}_{YYYYMMDD}.{ext}` with an anyone-with-link reader permission, and returns the link immediately to the accounts UI.
4. One notification per request (deduped via the `notifications` table) goes to the request's merchandiser — `created_by`, or a case-insensitive `users.email` match on `submitter_email` for public-form rows — as an in-app bell row + Web Push with the Drive link. HoM + super admins get an email if SMTP is configured.
5. **Fallback:** a 30-minute scheduler job sends a plain "payment processed" notice for requests processed >1 h ago with no TT copy and no notification; the link follows later as a "TT copy attached" notification when the upload happens.

Service worker note: `frontend/public/sw.js` is push-only — it must **never** gain a `fetch` handler (a previous caching SW caused response-clone errors).

---

## Key Business Rules

- **Supplier default gate:** If `defaulted_suppliers.is_active = true` for the selected supplier, the request form submit button is disabled and a red alert is shown. Only Finance Admin can resolve the flag.
- **Record locking:** Once `payment_processed`, `is_locked = true`. All edit endpoints return 423 for non-Super Admin users — except the TT copy upload (see above).
- **Status machine:** Transitions are defined in `backend/app/domain/rules/status_transitions.py`. Roles are checked per transition.
- **Soft deletes only:** No hard deletes anywhere. All tables have `is_deleted` / `is_active` columns.
- **Audit trail:** Every field change writes an `audit_logs` row with old/new value, user, IP address.
- **Request number format:** `ADT-YYYY-NNNNN` (sequential per calendar year).
- **List identifier:** request list tables display `sunshine_invoice_number || request_number` (`requestDisplayNumber()` in `frontend/src/lib/utils.ts`); the ADT number stays the permanent identifier on detail pages, audit logs, notifications, exports and TT-copy filenames.
- **Invoice number updates are super-admin-only:** `PATCH /requests/{id}` returns 403 if `sunshine_invoice_number` / `supplier_invoice_number` appear in the payload for any other role (setting them at creation via the forms is unaffected). The super-admin "Invoice Numbers" card on `/accounts/[id]` is the edit UI (works on locked rows). Every change lands in `audit_logs` as one row per field with old/new values — rendered on Admin → Audit Logs.
- **List search & sort:** `GET /requests` accepts `search` (ilike over request #, both invoice #s, supplier/customer name — joins added in `_apply_filters`) and `sort` (`newest` default / `oldest` / `amount_desc` / `amount_asc`). Non-paginated lists (accounts pending queue, HoM queue, drill-downs) filter/sort client-side via `requestMatchesSearch()` / `sortRequests()`.
- **Post-lock Ship Date:** `POST /requests/{id}/payment/ship-date` is the second deliberate lock exception (besides TT copy) — super_admin / finance_admin / accounts_team only, writes just `ship_date`, audited with before/after, reseeds the analytics snapshot (stops Cost of Fund accrual).

#!/usr/bin/env python3
"""
Migrate CSV data from the Sunshine Advance Deposit Tracker sheet into Supabase.

Usage:
    cd backend
    pip install psycopg2-binary python-dotenv
    python scripts/migrate_csv.py "C:/path/to/sheet.csv"

Reads MIGRATION_DATABASE_URL from backend/.env (direct Postgres, not pgbouncer).
All inserts run inside a single transaction — rolls back entirely on any error.
"""

import csv
import os
import sys
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2 not found. Run: pip install psycopg2-binary")
    sys.exit(1)

# ── Args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Usage: python scripts/migrate_csv.py <path_to_csv>")
    sys.exit(1)

CSV_PATH = sys.argv[1]

DB_URL = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    print("Error: MIGRATION_DATABASE_URL not set in backend/.env")
    sys.exit(1)

# psycopg2 requires postgresql:// not postgresql+asyncpg://
DB_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")

# ── Mappings ──────────────────────────────────────────────────────────────────
STATUS_MAP = {
    "Payment Processed":         "payment_processed",
    "Payment Processing":        "pending_payment",
    "Canceled by Merchandiser":  "cancelled_by_merchandiser",
    "Hold by Accounts":          "hold_by_accounts",
    "Hold by Merchandiser":      "hold_by_merchandiser",
}

# payment_details.payment_status only allows: processed, rejected, hold, or NULL
# (constrained by ck_payment_status check constraint)
PAYMENT_STATUS_MAP = {
    "payment_processed":          "processed",
    "pending_payment":            None,
    "cancelled_by_merchandiser":  "rejected",
    "hold_by_accounts":           "hold",
    "hold_by_merchandiser":       "hold",
}

# (csv_staff_name, placeholder_email, full_name)
MERCHANDISER_USERS = [
    ("Agnes",           "agnes@sunshine-tracker.local",           "Agnes"),
    ("Anil",            "anil@sunshine-tracker.local",            "Anil"),
    ("Asta",            "asta@sunshine-tracker.local",            "Asta"),
    ("Connie",          "connie@sunshine-tracker.local",          "Connie"),
    ("Harsh.Chauhan",   "harsh.chauhan@sunshine-tracker.local",   "Harsh Chauhan"),
    ("Joey",            "joey@sunshine-tracker.local",            "Joey"),
    ("Robin",           "robin@sunshine-tracker.local",           "Robin"),
    ("Shilpali",        "shilpali@sunshine-tracker.local",        "Shilpali"),
    ("Tricia",          "tricia@sunshine-tracker.local",          "Tricia"),
    ("Ulrica",          "ulrica@sunshine-tracker.local",          "Ulrica"),
    ("Yogesh.Tulsiani", "yogesh.tulsiani@sunshine-tracker.local", "Yogesh Tulsiani"),
]

# Accounts team users found in the CSV (col 29)
ACCOUNTS_USERS = [
    ("jignesh.oza@uma.inc", "Jignesh Oza"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_mon_date(val: str) -> Optional[date]:
    """DD-Mon-YYYY  e.g. 01-Apr-2026 or 1-Jan-2026"""
    val = val.strip()
    if not val:
        return None
    try:
        return datetime.strptime(val, "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_num_date(val: str) -> Optional[date]:
    """DD-MM-YYYY  e.g. 31-01-2026"""
    val = val.strip()
    if not val:
        return None
    try:
        return datetime.strptime(val, "%d-%m-%Y").date()
    except ValueError:
        return None


def parse_timestamp(val: str) -> Optional[datetime]:
    """M-D-YYYY HH:MM:SS or M-D-YYYY  e.g. 6-9-2026 17:52:53"""
    val = val.strip()
    if not val:
        return None
    for fmt in ("%m-%d-%Y %H:%M:%S", "%m-%d-%Y"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    return None


def clean_amount(val: str) -> Optional[float]:
    val = val.strip().replace(",", "")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load CSV (1 header row; blank trailing rows have no Key in col 0)
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        rows = [r for r in reader if r and r[0].strip()]

    print(f"Loaded {len(rows)} data rows from CSV.\n")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ── 1. Delete existing transaction data ───────────────────────────
        print("Truncating existing data (keeping users, system_config, payment_terms_master, form_links)...")
        cur.execute("""
            TRUNCATE TABLE
                analytics_snapshots,
                status_history,
                audit_logs,
                defaulted_suppliers,
                payment_details,
                deposit_requests,
                suppliers,
                customers,
                verticals
            RESTART IDENTITY CASCADE
        """)
        print("  Done.\n")

        # ── 2. Upsert users ───────────────────────────────────────────────
        print("Upserting users...")

        user_id_by_staff: dict[str, str] = {}  # staff_name → UUID str
        for staff_name, email, full_name in MERCHANDISER_USERS:
            uid = gen_uuid()
            cur.execute("""
                INSERT INTO users (id, email, full_name, role, is_active,
                                   onboarding_completed, ai_access_enabled,
                                   created_at, updated_at)
                VALUES (%s, %s, %s, 'merchandiser', TRUE, TRUE, FALSE, NOW(), NOW())
                ON CONFLICT (email) DO NOTHING
                RETURNING id
            """, (uid, email, full_name))
            row = cur.fetchone()
            if row:
                user_id_by_staff[staff_name] = str(row[0])
            else:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                user_id_by_staff[staff_name] = str(cur.fetchone()[0])

        accounts_id_by_email: dict[str, str] = {}  # email → UUID str
        for email, full_name in ACCOUNTS_USERS:
            uid = gen_uuid()
            cur.execute("""
                INSERT INTO users (id, email, full_name, role, is_active,
                                   onboarding_completed, ai_access_enabled,
                                   created_at, updated_at)
                VALUES (%s, %s, %s, 'accounts_team', TRUE, TRUE, FALSE, NOW(), NOW())
                ON CONFLICT (email) DO NOTHING
                RETURNING id
            """, (uid, email, full_name))
            row = cur.fetchone()
            if row:
                accounts_id_by_email[email] = str(row[0])
            else:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                accounts_id_by_email[email] = str(cur.fetchone()[0])

        print(f"  {len(user_id_by_staff)} merchandiser users, {len(accounts_id_by_email)} accounts users.\n")

        # ── 3. Insert customers ───────────────────────────────────────────
        print("Inserting customers...")
        customer_id_by_name: dict[str, str] = {}
        for name in sorted(set(r[9].strip() for r in rows if r[9].strip())):
            uid = gen_uuid()
            cur.execute("""
                INSERT INTO customers (id, name, is_active, created_at, updated_at)
                VALUES (%s, %s, TRUE, NOW(), NOW())
                RETURNING id
            """, (uid, name))
            customer_id_by_name[name] = str(cur.fetchone()[0])
        print(f"  {len(customer_id_by_name)} customers.\n")

        # ── 4. Insert verticals ───────────────────────────────────────────
        print("Inserting verticals...")
        vertical_id_by_name: dict[str, str] = {}
        for name in sorted(set(r[14].strip() for r in rows if r[14].strip())):
            uid = gen_uuid()
            cur.execute("""
                INSERT INTO verticals (id, name, is_active, created_at, updated_at)
                VALUES (%s, %s, TRUE, NOW(), NOW())
                RETURNING id
            """, (uid, name))
            vertical_id_by_name[name] = str(cur.fetchone()[0])
        print(f"  {len(vertical_id_by_name)} verticals.\n")

        # ── 5. Insert suppliers (dedup by lowercase name) ─────────────────
        print("Inserting suppliers...")
        supplier_id_by_name: dict[str, str] = {}  # original name → id
        seen_lower: dict[str, str] = {}           # lower(name) → id
        supplier_seq = 1
        for row in rows:
            name = row[6].strip()
            if not name:
                continue
            key = name.lower()
            if key not in seen_lower:
                uid = gen_uuid()
                prefix = "".join(c for c in name.upper() if c.isalpha())[:3] or "SUP"
                code = f"{prefix}-{supplier_seq:05d}"
                cur.execute("""
                    INSERT INTO suppliers (id, supplier_code, name, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                    RETURNING id
                """, (uid, code, name))
                sid = str(cur.fetchone()[0])
                seen_lower[key] = sid
                supplier_seq += 1
            supplier_id_by_name[name] = seen_lower[key]
        print(f"  {len(seen_lower)} unique suppliers.\n")

        # ── 6. Insert deposit_requests + payment_details + status_history ─
        print("Inserting requests...")
        req_count = pay_count = sh_count = 0
        warnings: list[tuple[int, str]] = []

        for row_idx, row in enumerate(rows, start=2):  # +2: 1 header + 1-indexed
            request_number   = row[0].strip()
            created_at       = parse_timestamp(row[1]) or datetime.utcnow()
            staff_name       = row[3].strip()
            submitter_email  = row[4].strip() or None
            payment_date_raw = row[5].strip()
            supplier_name    = row[6].strip()
            supplier_inv     = row[7].strip() or None
            sunshine_inv     = row[8].strip() or None
            customer_name    = row[9].strip()
            currency_raw     = row[10].strip()
            exchange_rate    = clean_amount(row[11])
            deposit_amount   = clean_amount(row[12])
            deposit_pct      = clean_amount(row[13])
            vertical_name    = row[14].strip()
            total_amount     = clean_amount(row[15])
            # row[16] (estimated shipment date) is no longer imported — the
            # column was removed by the 14 Jul 2026 change note (C5).
            est_etd_raw      = row[17].strip()
            remarks          = row[18].strip() or None
            status_raw       = row[23].strip()
            bank             = row[24].strip() or None
            ship_date_raw    = row[26].strip()
            acct_remarks     = row[27].strip() or None
            acct_ts_raw      = row[28].strip()
            acct_by_email    = row[29].strip() or None

            # Resolve status
            status_db = STATUS_MAP.get(status_raw)
            if not status_db:
                warnings.append((row_idx, f"Unknown status {repr(status_raw)} — skipping row"))
                continue

            # Resolve FKs
            currency      = "CNY" if currency_raw == "RMB" else (currency_raw or "USD")
            created_by_id = user_id_by_staff.get(staff_name)
            supplier_id   = supplier_id_by_name.get(supplier_name)
            customer_id   = customer_id_by_name.get(customer_name)
            vertical_id   = vertical_id_by_name.get(vertical_name)
            acct_user_id  = accounts_id_by_email.get(acct_by_email) if acct_by_email else None

            if not supplier_id:
                warnings.append((row_idx, f"Supplier not found: {repr(supplier_name)}"))
                continue
            if not customer_id:
                warnings.append((row_idx, f"Customer not found: {repr(customer_name)}"))
                continue
            if not vertical_id:
                warnings.append((row_idx, f"Vertical not found: {repr(vertical_name)}"))
                continue

            req_id = gen_uuid()
            pay_id = gen_uuid()
            sh_id  = gen_uuid()

            # deposit_requests
            cur.execute("""
                INSERT INTO deposit_requests (
                    id, request_number,
                    supplier_id, customer_id, vertical_id,
                    supplier_invoice_number, sunshine_invoice_number,
                    currency, exchange_rate,
                    deposit_amount, deposit_percentage,
                    total_supplier_invoice_amount,
                    estimated_etd,
                    remarks, submitter_email,
                    current_status, submission_source,
                    is_locked, is_deleted,
                    created_by, created_at, updated_at
                ) VALUES (
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s::currency_code, %s,
                    %s, %s,
                    %s,
                    %s,
                    %s, %s,
                    %s::request_status, %s::submission_source,
                    FALSE, FALSE,
                    %s, %s, %s
                )
            """, (
                req_id, request_number,
                supplier_id, customer_id, vertical_id,
                supplier_inv, sunshine_inv,
                currency, exchange_rate,
                deposit_amount, deposit_pct,
                total_amount,
                parse_mon_date(est_etd_raw),
                remarks, submitter_email,
                status_db, "google_sheet_sync",
                created_by_id, created_at, created_at,
            ))
            req_count += 1

            # payment_details (payment_status uses simplified 3-value constraint)
            acct_ts = parse_timestamp(acct_ts_raw) or datetime.utcnow()
            pay_status = PAYMENT_STATUS_MAP.get(status_db)
            cur.execute("""
                INSERT INTO payment_details (
                    id, deposit_request_id,
                    payment_date, bank,
                    payment_status, ship_date,
                    accounts_remarks,
                    updated_by, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                pay_id, req_id,
                parse_mon_date(payment_date_raw),
                bank,
                pay_status,
                parse_mon_date(ship_date_raw),
                acct_remarks,
                acct_user_id,
                acct_ts,
            ))
            pay_count += 1

            # status_history — one initial entry per request
            cur.execute("""
                INSERT INTO status_history (
                    id, deposit_request_id,
                    old_status, new_status,
                    remarks, changed_by, changed_at
                ) VALUES (
                    %s, %s,
                    NULL, %s::request_status,
                    NULL, %s, %s
                )
            """, (sh_id, req_id, status_db, created_by_id, created_at))
            sh_count += 1

        conn.commit()

        print(f"\n{'='*50}")
        print(f"  Migration complete.")
        print(f"{'='*50}")
        print(f"  Customers:        {len(customer_id_by_name)}")
        print(f"  Verticals:        {len(vertical_id_by_name)}")
        print(f"  Suppliers:        {len(seen_lower)}")
        print(f"  Deposit requests: {req_count}")
        print(f"  Payment details:  {pay_count}")
        print(f"  Status history:   {sh_count}")
        if warnings:
            print(f"\n  Warnings ({len(warnings)}):")
            for row_num, msg in warnings[:20]:
                print(f"    Row {row_num}: {msg}")
            if len(warnings) > 20:
                print(f"    ... and {len(warnings) - 20} more")
        print(f"\nNext step: trigger POST /analytics/recalculate to rebuild analytics snapshots.")

    except Exception as exc:
        conn.rollback()
        print(f"\n  Migration FAILED — rolled back.\n  Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

"""Go-live data wipe (2026-07-13).

Client signed off after live testing — clear all transactional/test data while
keeping users, roles, masters, and configuration untouched so the system keeps
working exactly as-is, just empty.

Phases:
  1. Backup every row of every table to be wiped into JSON files
     (backups/pre_go_live_wipe_2026-07-13/) and verify row counts match.
  2. Delete children-first inside ONE transaction, then verify final counts.

Run:  python scripts/go_live_wipe.py           (backup + counts only, dry run)
      python scripts/go_live_wipe.py --wipe    (backup, verify, then wipe)
"""

import asyncio
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BACKEND_DIR.parent / "backups" / "pre_go_live_wipe_2026-07-13"

# Children first, deposit_requests last (FK-safe delete order).
WIPE_TABLES = [
    "notifications",
    "audit_logs",
    "analytics_snapshots",
    "payment_details",
    "status_history",
    "merchandiser_actions",
    "accounts_actions",
    "google_form_submissions",
    "sync_logs",
    "defaulted_suppliers",
    "deposit_requests",
]

KEEP_TABLES = [
    "users",
    "suppliers",
    "customers",
    "verticals",
    "system_config",
    "payment_terms_master",
    "form_links",
    "push_subscriptions",
]


def load_dsn() -> str:
    """Read the direct (5432) DATABASE_URL from backend/.env, uncommented lines only."""
    direct = pooler = None
    for line in (BACKEND_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or not line.startswith("DATABASE_URL="):
            continue
        url = line.split("=", 1)[1].strip()
        if ":5432/" in url:
            direct = url
        else:
            pooler = url
    url = direct or pooler
    if not url:
        sys.exit("No active DATABASE_URL found in backend/.env")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return re.sub(r"\?.*$", "", url)  # asyncpg rejects the SQLAlchemy query params


def jsonable(v):
    if isinstance(v, (UUID, Decimal, datetime, date)):
        return str(v)
    return v


async def main() -> None:
    do_wipe = "--wipe" in sys.argv
    conn = await asyncpg.connect(load_dsn(), statement_cache_size=0)
    try:
        host = (await conn.fetchval("SELECT inet_server_addr()::text")) or "?"
        db = await conn.fetchval("SELECT current_database()")
        print(f"Connected to {db} ({host})\n")

        print("=== Row counts BEFORE ===")
        before = {}
        for t in WIPE_TABLES + KEEP_TABLES:
            before[t] = await conn.fetchval(f'SELECT COUNT(*) FROM "{t}"')
            tag = "WIPE" if t in WIPE_TABLES else "KEEP"
            print(f"  [{tag}] {t}: {before[t]}")

        # Phase 1 — backup
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Backing up to {BACKUP_DIR} ===")
        for t in WIPE_TABLES:
            rows = await conn.fetch(f'SELECT * FROM "{t}"')
            data = [{k: jsonable(v) for k, v in r.items()} for r in rows]
            out = BACKUP_DIR / f"{t}.json"
            out.write_text(json.dumps(data, indent=1, default=str))
            if len(data) != before[t]:
                sys.exit(f"ABORT: backup of {t} has {len(data)} rows, expected {before[t]}")
            print(f"  {t}: {len(data)} rows -> {out.name}")
        (BACKUP_DIR / "_meta.json").write_text(json.dumps({
            "taken_at_utc": datetime.utcnow().isoformat() + "Z",
            "database": db,
            "reason": "go-live wipe after client sign-off",
            "row_counts_before": before,
        }, indent=1))
        print("Backup verified: all row counts match.")

        if not do_wipe:
            print("\nDry run only (no --wipe flag). Nothing deleted.")
            return

        # Phase 2 — wipe, single transaction
        print("\n=== Wiping (single transaction) ===")
        async with conn.transaction():
            for t in WIPE_TABLES:
                res = await conn.execute(f'DELETE FROM "{t}"')
                print(f"  {t}: {res}")

        print("\n=== Row counts AFTER ===")
        ok = True
        for t in WIPE_TABLES + KEEP_TABLES:
            n = await conn.fetchval(f'SELECT COUNT(*) FROM "{t}"')
            tag = "WIPE" if t in WIPE_TABLES else "KEEP"
            print(f"  [{tag}] {t}: {n}")
            if t in WIPE_TABLES and n != 0:
                ok = False
            if t in KEEP_TABLES and n != before[t]:
                ok = False
        print("\n" + ("SUCCESS: wiped tables empty, kept tables untouched."
                      if ok else "WARNING: post-wipe counts unexpected — review above."))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Hard-delete the 29 deactivated users, keeping only the 6 active staff (2026-07-13).

Client asked (after go-live) to physically remove the deactivated accounts that
still show in the raw Supabase table. This is a genuine hard delete (against the
usual soft-delete convention) — done deliberately at the client's request, with a
full JSON backup first.

Keeps exactly these 6 by email; deletes everyone else. SAFETY: aborts if any user
it is about to delete is still is_active=true (guards against catching a newly
added real account).

Run:  python scripts/delete_inactive_users.py           (backup + preview, no delete)
      python scripts/delete_inactive_users.py --delete   (backup, verify, delete)
"""

import asyncio
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from go_live_wipe import load_dsn  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "backups" / "user_hard_delete_2026-07-13"

KEEP_EMAILS = {
    "joshiyash666@gmail.com",        # Yash Joshi (super_admin)
    "jignesh.oza@uma.inc",           # Jignesh Oza (super_admin)
    "rutvik.vaishnav@africonact.com",  # Rutvik (super_admin)
    "pradip@sunshineltd.com",        # Pradip (head_of_merchandiser)
    "susie@sunshineltd.com",         # Susie (accounts_team)
    "yogesh@sunshineltd.com",        # Yogesh Puri (accounts_team)
}


def jsonable(v):
    if isinstance(v, (UUID, Decimal, datetime, date)):
        return str(v)
    return v


async def main() -> None:
    do_delete = "--delete" in sys.argv
    conn = await asyncpg.connect(load_dsn(), statement_cache_size=0)
    try:
        keep = list(KEEP_EMAILS)
        targets = await conn.fetch(
            "SELECT id, email, full_name, role, is_active FROM users "
            "WHERE email != ALL($1::text[]) ORDER BY email",
            keep,
        )
        print(f"Users to DELETE: {len(targets)}")
        active_caught = [r for r in targets if r["is_active"]]
        for r in targets:
            flag = "  <-- ACTIVE! " if r["is_active"] else ""
            print(f"  {r['email']:42} | {r['role']:20} | active={r['is_active']}{flag}")

        # Safety guard
        if active_caught:
            sys.exit(f"\nABORT: {len(active_caught)} account(s) to be deleted are still ACTIVE. "
                     "Refusing to delete active users.")

        kept = await conn.fetch(
            "SELECT email, role FROM users WHERE email = ANY($1::text[]) ORDER BY email", keep)
        print(f"\nUsers to KEEP: {len(kept)}")
        for r in kept:
            print(f"  {r['email']:42} | {r['role']}")
        if len(kept) != 6:
            sys.exit(f"\nABORT: expected to keep 6 users, found {len(kept)} matching the keep-list.")

        target_ids = [r["id"] for r in targets]

        # Backup the target users + any push_subscriptions they own
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        users_full = await conn.fetch(
            "SELECT * FROM users WHERE id = ANY($1::uuid[])", target_ids)
        subs = await conn.fetch(
            "SELECT * FROM push_subscriptions WHERE user_id = ANY($1::uuid[])", target_ids)
        (BACKUP_DIR / "deleted_users.json").write_text(
            json.dumps([{k: jsonable(v) for k, v in r.items()} for r in users_full], indent=1))
        (BACKUP_DIR / "deleted_push_subscriptions.json").write_text(
            json.dumps([{k: jsonable(v) for k, v in r.items()} for r in subs], indent=1))
        print(f"\nBacked up {len(users_full)} users + {len(subs)} push_subscriptions to {BACKUP_DIR}")

        if not do_delete:
            print("\nDry run only (no --delete flag). Nothing deleted.")
            return

        async with conn.transaction():
            s = await conn.execute(
                "DELETE FROM push_subscriptions WHERE user_id = ANY($1::uuid[])", target_ids)
            print(f"\nDeleted push_subscriptions: {s}")
            d = await conn.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", target_ids)
            print(f"Deleted users: {d}")

        remaining = await conn.fetch("SELECT email, full_name, role, is_active FROM users ORDER BY email")
        print(f"\n=== Users remaining: {len(remaining)} ===")
        for r in remaining:
            print(f"  {r['email']:42} | {(r['full_name'] or ''):18} | {r['role']:20} | active={r['is_active']}")
        print("\nSUCCESS." if len(remaining) == 6 else f"\nWARNING: expected 6 remaining, got {len(remaining)}.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

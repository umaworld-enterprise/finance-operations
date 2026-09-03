"""
One-time ownership fix (2 Sep 2026): Rutwik entered the 1–2 Sep requests from
his own account — reassign each request's created_by to its real merchandiser,
matched by Sunshine Invoice Number (with the supplier proforma number as a
tie-breaker / sanity check).

Safe by construction:
- Only touches created_by on the listed requests — nothing else changes.
- Users are looked up by email and NEVER created or modified.
- Ambiguous or missing matches are reported and SKIPPED.
- Every change writes a field-level audit row (old → new owner).
- --dry-run prints the full plan without writing.

Usage (from backend/):
    python -m scripts.reassign_request_owners --dry-run
    python -m scripts.reassign_request_owners
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.deposit_request import DepositRequest
from app.models.enums import AuditAction
from app.models.masters import User

settings = get_settings()

# (sunshine_invoice_number, supplier_invoice_number, new_owner_email) — from
# the tracker rows of 1–2 Sep 2026, exactly as entered (typos included:
# "20026-27", "396" — they must match what is stored).
REASSIGNMENTS: list[tuple[str, str, str]] = [
    ("1156", "zy0011/0013/0015/0017", "tricia@sunshineltd.com"),
    ("1895/3817/2026-27", "2026EX0196", "anil@sunshineltd.com"),
    ("1871/3794/20026-27", "EST-001761", "joey@sunshineltd.com"),
    ("1893/5005/26-27", "AL/IO/SPD/ROC/2025/01", "shilpali@sunshineltd.com"),
    ("1872/3795/2026-27", "EST-001755", "joey@sunshineltd.com"),
    ("1873/396/2026-27", "EST-001756", "joey@sunshineltd.com"),
    ("1874/3797/2026-27", "EST-001757", "joey@sunshineltd.com"),
    ("1907", "GCINV260825-1", "shilpali@sunshineltd.com"),
    ("938/3299/2026/27", "JP-SS-WM-2603BN", "yogesh.tulsiani@sunshineltd.com"),
    ("1882/3806/2026-27", "26FAWT1345", "joey@sunshineltd.com"),
    ("1609/3656/2026-27", "CMP/THT/GN-2603", "joey@sunshineltd.com"),
    ("862/3261/2026-27", "FMSUNS260528TBR-1", "joey@sunshineltd.com"),
    ("863/3262/2026-27", "FMSUNS260528TBR-1", "joey@sunshineltd.com"),
    ("864/3263/2026-27", "FMSUNS260528TBR-1", "joey@sunshineltd.com"),
    ("865/3264/2026-27", "FMSUNS260528TBR-1", "joey@sunshineltd.com"),
    ("929/3265/2026-27", "FMSUNS260528TBR-1", "joey@sunshineltd.com"),
    ("1731/3725/2026-27", "PI260903", "joey@sunshineltd.com"),
    ("1898/3819/2026-27", "26YCA110", "joey@sunshineltd.com"),
    ("1899/3820/2026-27", "26YCA111", "joey@sunshineltd.com"),
    ("1900/3821/2026-27", "26YCA112", "joey@sunshineltd.com"),
    ("1904/3828/2026-27", "128669", "anil@sunshineltd.com"),
    ("1905/3829/2026-27", "128670", "anil@sunshineltd.com"),
    ("1908/3830/2026-27", "TY26090454", "robin@sunshineltd.com"),
    ("1909/3831/2026-27", "TY26090455", "robin@sunshineltd.com"),
    ("1913/3832/2026-27", "HMA/PI/1069/2026-27", "anil@sunshineltd.com"),
    ("1914/3833/2026-27", "HMA/PI/1070/2026-27", "anil@sunshineltd.com"),
]


async def run(dry_run: bool) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        users = {
            u.email.lower(): u
            for u in (await session.execute(select(User))).scalars()
        }
        changed = skipped = unchanged = 0
        for sunshine, supplier_inv, email in REASSIGNMENTS:
            owner = users.get(email.lower())
            if owner is None:
                print(f"SKIP  {sunshine}: no user with email {email}")
                skipped += 1
                continue
            matches = list(
                (
                    await session.execute(
                        select(DepositRequest).where(
                            func.lower(func.trim(DepositRequest.sunshine_invoice_number))
                            == sunshine.lower(),
                            DepositRequest.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalars()
            )
            if len(matches) > 1:
                # Disambiguate on the supplier proforma number.
                narrowed = [
                    r
                    for r in matches
                    if (r.supplier_invoice_number or "").strip().lower()
                    == supplier_inv.lower()
                ]
                if len(narrowed) == 1:
                    matches = narrowed
            if len(matches) == 0:
                print(f"SKIP  {sunshine}: no request found")
                skipped += 1
                continue
            if len(matches) > 1:
                print(f"SKIP  {sunshine}: {len(matches)} requests match — resolve manually")
                skipped += 1
                continue

            req = matches[0]
            if (req.supplier_invoice_number or "").strip().lower() != supplier_inv.lower():
                print(
                    f"NOTE  {req.request_number} ({sunshine}): stored proforma "
                    f"'{req.supplier_invoice_number}' differs from the list's "
                    f"'{supplier_inv}' — matched on sunshine number alone."
                )
            if req.created_by == owner.id:
                print(f"OK    {req.request_number} ({sunshine}): already owned by {email}")
                unchanged += 1
                continue

            old_owner = req.created_by
            old_email = next(
                (u.email for u in users.values() if u.id == old_owner), str(old_owner)
            )
            print(f"MOVE  {req.request_number} ({sunshine}): {old_email} → {email}")
            if not dry_run:
                session.add(
                    AuditLog(
                        entity_name="deposit_requests",
                        entity_id=req.id,
                        field_name="created_by",
                        old_value=old_email,
                        new_value=email,
                        action=AuditAction.UPDATE,
                        # The previous owner account performed the original
                        # entry — recorded as the acting user of this fix.
                        changed_by=old_owner or owner.id,
                    )
                )
                req.created_by = owner.id
                # Keep the submitter reference consistent with the new owner.
                if req.submitter_email:
                    req.submitter_email = email
            changed += 1

        print(
            f"\n{changed} reassigned, {unchanged} already correct, {skipped} skipped."
        )
        if dry_run:
            print("DRY RUN — nothing was written.")
        else:
            await session.commit()
            print("Committed.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))

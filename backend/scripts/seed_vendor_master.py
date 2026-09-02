"""
Vendor Master import (FY 2025-26) — updates the supplier / vertical /
customer masters from seed_data/Vendor Master (FY 2025-26).csv WITHOUT
creating duplicates. Safe to run repeatedly (idempotent) and touches
NOTHING else — no users, no requests, no deletions.

Matching: by name, case-insensitively, with whitespace collapsed
("AAB  (CHINA)" == "aab (china)"). Rows already present are left alone;
a matching row that was deactivated is reactivated (the current FY vendor
master is the live list) unless --no-reactivate is passed. Missing rows are
inserted; new suppliers get a generated unique code following the existing
"ABC-00042" convention (3 alpha chars of the name + running number).

Usage (from backend/):
    python -m scripts.seed_vendor_master --dry-run   # report only
    python -m scripts.seed_vendor_master             # apply

Requires DATABASE_URL in the environment (or .env), like scripts.seed.
"""

import argparse
import asyncio
import csv
import os
import re
import sys
from pathlib import Path

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.masters import Customer, Supplier, Vertical

settings = get_settings()

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "seed_data" / "Vendor Master (FY 2025-26).csv"


def norm(name: str) -> str:
    """Case- and whitespace-insensitive matching key."""
    return " ".join(name.split()).lower()


def read_csv(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Columns: 0 = Supplier, 4 = Verticle, 6 = Customers (header + blank
    row skipped). Each column is an independent list."""
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    suppliers, verticals, customers = [], [], []
    for row in rows[1:]:
        if len(row) > 0 and row[0].strip() and norm(row[0]) != "supplier":
            suppliers.append(" ".join(row[0].split()))
        if len(row) > 4 and row[4].strip() and norm(row[4]) != "verticle":
            verticals.append(" ".join(row[4].split()))
        if len(row) > 6 and row[6].strip() and norm(row[6]) != "customers":
            customers.append(" ".join(row[6].split()))

    def dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out = []
        for item in items:
            if norm(item) not in seen:
                seen.add(norm(item))
                out.append(item)
        return out

    return dedupe(suppliers), dedupe(verticals), dedupe(customers)


def next_code_seq(existing_codes: list[str]) -> int:
    """Continue the running number above every existing 'XXX-00042' code."""
    top = 0
    for code in existing_codes:
        m = re.search(r"-(\d+)$", code or "")
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


def make_code(name: str, seq: int, taken: set[str]) -> tuple[str, int]:
    prefix = "".join(c for c in name.upper() if c.isalpha())[:3] or "SUP"
    while True:
        code = f"{prefix}-{seq:05d}"
        if code not in taken:
            taken.add(code)
            return code, seq + 1
        seq += 1


async def run(csv_path: Path, dry_run: bool, reactivate: bool) -> None:
    suppliers, verticals, customers = read_csv(csv_path)
    print(f"CSV: {len(suppliers)} suppliers, {len(verticals)} verticals, {len(customers)} customers\n")

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        stats: dict[str, dict[str, int]] = {}
        plans: list[tuple[str, str, str]] = []  # (kind, action, name)

        async def sync_simple(kind: str, model, names: list[str]) -> None:
            existing = list((await session.execute(select(model))).scalars().all())
            by_key = {norm(row.name): row for row in existing}
            stat = stats.setdefault(kind, {"added": 0, "reactivated": 0, "unchanged": 0})
            for name in names:
                row = by_key.get(norm(name))
                if row is None:
                    stat["added"] += 1
                    plans.append((kind, "ADD", name))
                    if not dry_run:
                        session.add(model(name=name, is_active=True))
                elif not row.is_active and reactivate:
                    stat["reactivated"] += 1
                    plans.append((kind, "REACTIVATE", name))
                    if not dry_run:
                        row.is_active = True
                else:
                    stat["unchanged"] += 1

        # Suppliers carry a mandatory unique code.
        existing_suppliers = list((await session.execute(select(Supplier))).scalars().all())
        supplier_by_key = {norm(s.name): s for s in existing_suppliers}
        taken_codes = {s.supplier_code for s in existing_suppliers}
        seq = next_code_seq(list(taken_codes))
        stat = stats.setdefault("supplier", {"added": 0, "reactivated": 0, "unchanged": 0})
        for name in suppliers:
            row = supplier_by_key.get(norm(name))
            if row is None:
                code, seq = make_code(name, seq, taken_codes)
                stat["added"] += 1
                plans.append(("supplier", "ADD", f"{name}  [{code}]"))
                if not dry_run:
                    session.add(Supplier(supplier_code=code, name=name, is_active=True))
            elif not row.is_active and reactivate:
                stat["reactivated"] += 1
                plans.append(("supplier", "REACTIVATE", name))
                if not dry_run:
                    row.is_active = True
            else:
                stat["unchanged"] += 1

        await sync_simple("vertical", Vertical, verticals)
        await sync_simple("customer", Customer, customers)

        for kind, action, name in plans:
            print(f"  {action:<10} {kind:<9} {name}")
        print()
        for kind, stat in stats.items():
            print(
                f"{kind}s: {stat['added']} added, {stat['reactivated']} reactivated, "
                f"{stat['unchanged']} already present"
            )

        if dry_run:
            print("\nDRY RUN — nothing was written.")
        else:
            await session.commit()
            print("\nCommitted.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--no-reactivate", action="store_true",
        help="leave deactivated rows inactive even when the CSV lists them",
    )
    args = parser.parse_args()
    if not args.csv.exists():
        sys.exit(f"CSV not found: {args.csv}")
    asyncio.run(run(args.csv, dry_run=args.dry_run, reactivate=not args.no_reactivate))

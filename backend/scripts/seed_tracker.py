"""
Deposit tracker import — populates deposit requests (plus tranches, payment
details and status history) from seed_data/Deposit Sunshine Tracker - Form
Submission.csv. One-time load into a FRESH database: it REFUSES to run while
any deposit request exists (wipe entry data first), so it can never
double-import.

Scoping decisions (2 Sep 2026):
- Request numbers are generated sequentially in request-date order, the year
  part following each request's calendar year (Dep-2025-0001…, restarting at
  Dep-2026-0001 in January) — new in-app requests continue after the max.
- Status mapping: "Payment Processed" → payment_processed + locked, tranche 1
  PAID; "Canceled by Merchandiser" / Cancellation column → cancelled;
  "Hold by …" → the matching hold; BLANK → pending_payment (unpaid tranche).
- Missing staff emails become ACTIVE merchandiser users (never modifies
  existing users). Suppliers / customers / verticals are get-or-created by
  normalised name, same rules as scripts.seed_vendor_master.

Usage (from backend/):
    python -m scripts.seed_tracker --dry-run   # report only
    python -m scripts.seed_tracker             # apply
"""

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.deposit_request import DepositRequest
from app.models.enums import (
    CurrencyCode,
    RequestStatus,
    SubmissionSource,
    TrancheStatus,
    UserRole,
)
from app.models.masters import Customer, Supplier, User, Vertical
from app.models.payment import PaymentDetails
from app.models.tranche import PaymentTranche
from app.models.workflow import StatusHistory
from scripts.seed_vendor_master import make_code, next_code_seq, norm

settings = get_settings()

DEFAULT_CSV = (
    Path(__file__).resolve().parent.parent
    / "seed_data"
    / "Deposit Sunshine Tracker - Form Submission.csv"
)

_STATUS_MAP = {
    "payment processed": RequestStatus.PAYMENT_PROCESSED,
    "canceled by merchandiser": RequestStatus.CANCELLED_BY_MERCHANDISER,
    "cancelled by merchandiser": RequestStatus.CANCELLED_BY_MERCHANDISER,
    "hold by merchandiser": RequestStatus.HOLD_BY_MERCHANDISER,
    "hold by accounts": RequestStatus.HOLD_BY_ACCOUNTS,
}

_BANK_MAP = {"CIT": "CITI", "CIIT": "CITI", "CITI": "CITI", "DBS": "DBS", "SCB": "SCB"}

_CURRENCY_MAP = {"USD": CurrencyCode.USD, "EUR": CurrencyCode.EUR, "RMB": CurrencyCode.CNY}


def parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_ts(value: str):
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> Decimal | None:
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def normalize_bank(value: str) -> str | None:
    cleaned = (value or "").strip().strip("'\"").upper()
    return _BANK_MAP.get(cleaned, cleaned or None)


def map_status(status_raw: str, cancellation: str) -> RequestStatus:
    status = _STATUS_MAP.get((status_raw or "").strip().lower())
    if status is not None:
        return status
    if (cancellation or "").strip():
        return RequestStatus.CANCELLED_BY_MERCHANDISER
    return RequestStatus.PENDING_PAYMENT


async def run(csv_path: Path, dry_run: bool) -> None:
    raw = list(csv.reader(open(csv_path, encoding="utf-8-sig")))
    rows = [r for r in raw[1:] if any(c.strip() for c in r)]
    print(f"CSV rows: {len(rows)}")

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        existing_requests = (
            await session.execute(select(func.count()).select_from(DepositRequest))
        ).scalar_one()
        if existing_requests:
            sys.exit(
                f"REFUSING to run: {existing_requests} deposit requests already "
                "exist. This is a one-time load into a fresh database — clear "
                "the entry data first."
            )

        # ── Reference data (get-or-create; users NEVER modified) ────────────
        users = {u.email.lower(): u for u in (await session.execute(select(User))).scalars()}
        suppliers = {norm(s.name): s for s in (await session.execute(select(Supplier))).scalars()}
        customers = {norm(c.name): c for c in (await session.execute(select(Customer))).scalars()}
        verticals = {norm(v.name): v for v in (await session.execute(select(Vertical))).scalars()}
        taken_codes = {s.supplier_code for s in suppliers.values()}
        code_seq = next_code_seq(list(taken_codes))

        created: dict[str, int] = {"user": 0, "supplier": 0, "customer": 0, "vertical": 0}
        warnings: list[str] = []

        def get_user(email: str, staff: str) -> User:
            key = email.strip().lower()
            user = users.get(key)
            if user is None:
                full_name = " ".join(staff.replace(".", " ").split()) or key.split("@")[0]
                user = User(
                    email=key, full_name=full_name,
                    role=UserRole.MERCHANDISER, is_active=True,
                )
                session.add(user)
                users[key] = user
                created["user"] += 1
            return user

        def get_supplier(name: str) -> Supplier:
            nonlocal code_seq
            clean = " ".join(name.split())
            row = suppliers.get(norm(clean))
            if row is None:
                code, code_seq = make_code(clean, code_seq, taken_codes)
                row = Supplier(supplier_code=code, name=clean, is_active=True)
                session.add(row)
                suppliers[norm(clean)] = row
                created["supplier"] += 1
            return row

        def get_simple(model, cache: dict, name: str, kind: str):
            clean = " ".join(name.split())
            row = cache.get(norm(clean))
            if row is None:
                row = model(name=clean, is_active=True)
                session.add(row)
                cache[norm(clean)] = row
                created[kind] += 1
            return row

        if not dry_run:
            # Flush reference rows so FKs resolve.
            pass

        # ── Requests, numbered by request date ──────────────────────────────
        def sort_key(row):  # type: ignore[no-untyped-def]
            return (
                parse_date(row[1]) or datetime(2100, 1, 1).date(),
                parse_ts(row[0]) or datetime(2100, 1, 1, tzinfo=timezone.utc),
            )

        rows.sort(key=sort_key)
        counters: dict[int, int] = {}
        status_counts: dict[str, int] = {}
        imported = 0

        for line_no, row in enumerate(rows, start=2):
            request_date = parse_date(row[1])
            created_at = parse_ts(row[0]) or (
                datetime.combine(request_date, datetime.min.time(), tzinfo=timezone.utc)
                if request_date
                else None
            )
            if request_date is None or created_at is None:
                warnings.append(f"line {line_no}: unparseable request date/timestamp — SKIPPED")
                continue
            deposit = parse_amount(row[13])
            total = parse_amount(row[17])
            if deposit is None or total is None:
                warnings.append(f"line {line_no}: unparseable amount — SKIPPED")
                continue

            status = map_status(row[22], row[20])
            status_counts[status.value] = status_counts.get(status.value, 0) + 1
            payment_date = parse_date(row[4])
            ship_date = parse_date(row[25])
            est_etd = parse_date(row[19]) or parse_date(row[18])
            bank = normalize_bank(row[23])
            currency = _CURRENCY_MAP.get((row[10] or "").strip().upper())
            if (row[10] or "").strip() and currency is None:
                warnings.append(f"line {line_no}: unknown currency '{row[10]}' — stored NULL")
            pct = parse_amount(row[15])
            if pct is None and total:
                pct = (deposit / total * 100).quantize(Decimal("0.01"))
            processed = status == RequestStatus.PAYMENT_PROCESSED
            if processed and payment_date is None:
                warnings.append(
                    f"line {line_no}: Payment Processed without a payment date — "
                    "imported paid with payment date NULL (fix in app if needed)"
                )

            year = request_date.year
            counters[year] = counters.get(year, 0) + 1
            request_number = f"Dep-{year}-{counters[year]:04d}"

            if dry_run:
                get_user(row[2], row[3])  # count creations
                if norm(" ".join(row[6].split())) not in suppliers:
                    created["supplier"] += 1
                    suppliers[norm(" ".join(row[6].split()))] = object()  # type: ignore[assignment]
                if norm(" ".join(row[9].split())) not in customers:
                    created["customer"] += 1
                    customers[norm(" ".join(row[9].split()))] = object()  # type: ignore[assignment]
                if norm(" ".join(row[16].split())) not in verticals:
                    created["vertical"] += 1
                    verticals[norm(" ".join(row[16].split()))] = object()  # type: ignore[assignment]
                imported += 1
                continue

            owner = get_user(row[2], row[3])
            supplier = get_supplier(row[6])
            customer = get_simple(Customer, customers, row[9], "customer")
            vertical = get_simple(Vertical, verticals, row[16], "vertical")
            await session.flush()  # ids for the FKs below

            request = DepositRequest(
                request_number=request_number,
                supplier_id=supplier.id,
                customer_id=customer.id,
                vertical_id=vertical.id,
                supplier_invoice_number=(row[7] or "").strip() or None,
                sunshine_invoice_number=(row[8] or "").strip() or None,
                currency=currency,
                deposit_amount=deposit,
                deposit_percentage=pct,
                total_supplier_invoice_amount=total,
                estimated_etd=est_etd,
                submitter_email=(row[2] or "").strip() or None,
                remarks=(row[21] or "").strip() or None,
                submission_source=SubmissionSource.GOOGLE_FORM,
                current_status=status,
                is_locked=processed,
                created_by=owner.id,
            )
            request.created_at = created_at
            session.add(request)
            await session.flush()

            paid_at = (
                datetime.combine(payment_date, datetime.min.time(), tzinfo=timezone.utc)
                if payment_date
                else created_at
            )
            session.add(
                PaymentTranche(
                    deposit_request_id=request.id,
                    tranche_number=1,
                    amount=deposit,
                    tentative_payment_date=None,
                    status=TrancheStatus.PAID if processed else TrancheStatus.UNPAID,
                    paid_at=paid_at if processed else None,
                    payment_date=payment_date if processed else None,
                    bank=bank if processed else None,
                    is_legacy=True,
                    released_at=created_at,
                )
            )
            if processed or payment_date or ship_date or (row[26] or "").strip():
                session.add(
                    PaymentDetails(
                        deposit_request_id=request.id,
                        payment_date=payment_date,
                        bank=bank,
                        payment_status="processed" if processed else None,
                        ship_date=ship_date,
                        accounts_remarks=(row[26] or "").strip() or None,
                    )
                )
            session.add(
                StatusHistory(
                    deposit_request_id=request.id,
                    old_status=None,
                    new_status=status,
                    changed_by=owner.id,
                    changed_at=created_at,
                )
            )
            imported += 1

        print(f"\nrequests imported: {imported}")
        for value, count in sorted(status_counts.items()):
            print(f"  {value}: {count}")
        print(
            f"created: {created['user']} users, {created['supplier']} suppliers, "
            f"{created['customer']} customers, {created['vertical']} verticals"
        )
        if counters:
            for year in sorted(counters):
                print(f"  numbering Dep-{year}-0001 … Dep-{year}-{counters[year]:04d}")
        if warnings:
            print(f"\nwarnings ({len(warnings)}):")
            for w in warnings:
                print(f"  {w}")

        if dry_run:
            print("\nDRY RUN — nothing was written.")
        else:
            await session.commit()
            print(
                "\nCommitted. Analytics snapshots refresh via the 30-minute "
                "scheduler, or immediately via the admin Recalculate button."
            )
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()
    if not args.csv.exists():
        sys.exit(f"CSV not found: {args.csv}")
    asyncio.run(run(args.csv, dry_run=args.dry_run))

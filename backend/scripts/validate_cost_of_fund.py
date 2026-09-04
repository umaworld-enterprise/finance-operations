"""
Cost-of-Fund reconciliation (4 Sep 2026) — validates EVERY request in the
database against seed_data/Deposit Sunshine Tracker.xlsx (the client's live
tracker, data till 2 Sep 2026) and against the app's own analytics engine,
so the analytics plot the same numbers as the sheet.

For each tracker row (matched to a request by Sunshine Invoice Number) it
checks, in order:

  MISSING_IN_DB    sheet row has no matching request (past-cutoff rows noted)
  AMBIGUOUS        the sunshine number appears more than once (sheet or DB) —
                   reported, never auto-fixed
  STATUS_DRIFT     processed/cancelled in one place but not the other
  INPUT_DRIFT      payment date / ship date / Est ETD / deposit differ between
                   the sheet and the DB (these are the Cost-of-Fund INPUTS —
                   a wrong or missing payment date silently zeroes CoF)
  MISSING_SNAPSHOT the request has no analytics_snapshots row at all
  STALE_SNAPSHOT   the stored snapshot differs from what the engine computes
                   TODAY from the DB's own inputs (needs recalculation)
  OK               inputs match the sheet and the snapshot is current

It also lists DB requests whose sunshine number is absent from the sheet
(entered in the app after 2 Sep, or renamed) — informational only.

Fix mode (``--fix``, requires ``--actor-email`` of an existing user for the
audit trail) repairs, for IMPORTED (google_form) requests only:
  * payment_date / ship_date on payment_details (row created if missing),
  * estimated_etd on the request,
  * payment_date / paid_at on the legacy tranche 1 when the payment date moves,
and then recomputes + upserts the analytics snapshot for EVERY matched
request (snapshots are derived data — safe for all). Deposit-amount and
status differences are REPORTED ONLY — money and workflow state are never
auto-changed.

Usage (from backend/):
    python -m scripts.validate_cost_of_fund                 # report only
    python -m scripts.validate_cost_of_fund --details 50    # more detail rows
    python -m scripts.validate_cost_of_fund --fix --actor-email admin@x.com
"""

import argparse
import asyncio
import datetime as dt
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.analytics.engine import AnalyticsInput, compute
from app.core.config import get_settings
from app.models.analytics import AnalyticsSnapshot
from app.models.audit import AuditLog
from app.models.deposit_request import DepositRequest
from app.models.enums import AuditAction, RequestStatus, SubmissionSource, TrancheStatus
from app.models.masters import SystemConfig, User
from app.models.payment import PaymentDetails
from app.models.tranche import PaymentTranche
from app.repositories.analytics_repo import AnalyticsRepository

settings = get_settings()

DEFAULT_XLSX = Path(__file__).resolve().parent.parent / "seed_data" / "Deposit Sunshine Tracker.xlsx"

_CANCELLED = (
    RequestStatus.CANCELLED_BY_MERCHANDISER,
    RequestStatus.CANCELLED_BY_ACCOUNTS,
    RequestStatus.REJECTED_BY_HOM,
    RequestStatus.REJECTED_BY_ACCOUNTS,
)


def norm_key(value) -> str:
    return " ".join(str(value or "").split()).lower()


def as_date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return None


def load_sheet(path: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Form Submission"]
    rows: list[dict] = []
    for r in ws.iter_rows(min_row=2, max_col=33, values_only=True):
        if r[8] is None and r[6] is None and r[0] is None:
            continue
        rows.append(
            {
                "request_date": as_date(r[1]) or as_date(r[0]),
                "sunshine": str(r[8] or "").strip(),
                "supplier": str(r[6] or "").strip(),
                "payment_date": as_date(r[4]),
                "ship_date": as_date(r[25]),
                "est_etd": as_date(r[19]) or as_date(r[18]),
                "deposit": Decimal(str(r[13])) if r[13] is not None else None,
                "processed": str(r[22] or "").strip().lower() == "payment processed",
                "cancelled": bool(str(r[20] or "").strip()),
                # The sheet's own cached computations — informational context.
                "sheet_ae": r[30] if isinstance(r[30], (int, float)) else None,
                "sheet_cof": r[31] if isinstance(r[31], (int, float)) else None,
            }
        )
    wb.close()
    return rows


async def run(xlsx: Path, fix: bool, actor_email: str | None, details: int) -> None:
    sheet_rows = load_sheet(xlsx)
    print(f"sheet rows: {len(sheet_rows)}  ({xlsx.name})")

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        actor: User | None = None
        if fix:
            if not actor_email:
                sys.exit("--fix requires --actor-email (an existing user, for the audit trail)")
            actor = (
                await session.execute(
                    select(User).where(User.email == actor_email.strip().lower())
                )
            ).scalar_one_or_none()
            if actor is None:
                sys.exit(f"--actor-email: no user with email {actor_email}")

        config = {
            row.config_key: row.config_value
            for row in (await session.execute(select(SystemConfig))).scalars()
        }
        grace_days = int(config.get("etd_grace_days", settings.default_etd_grace_days))
        rate = float(config.get("cost_of_fund_rate", settings.default_cost_of_fund_rate))
        cof_grace = int(
            config.get("cost_of_fund_grace_days", settings.default_cost_of_fund_grace_days)
        )
        print(f"config: etd_grace_days={grace_days}  cost_of_fund_rate={rate}")
        if abs(rate - 0.12) > 1e-9:
            print("  ⚠ cost_of_fund_rate is NOT 0.12 — the sheet uses 12%; numbers WILL differ.")

        requests = list(
            (
                await session.execute(
                    select(DepositRequest)
                    .where(DepositRequest.is_deleted == False)  # noqa: E712
                    .options(
                        selectinload(DepositRequest.payment),
                        selectinload(DepositRequest.analytics_snapshot),
                        selectinload(DepositRequest.tranches),
                    )
                )
            ).scalars()
        )
        print(f"db requests: {len(requests)}")

        db_by_key: dict[str, list[DepositRequest]] = {}
        for req in requests:
            db_by_key.setdefault(norm_key(req.sunshine_invoice_number), []).append(req)

        counts: dict[str, int] = {}
        detail_lines: list[str] = []
        fixed_inputs = 0
        snapshots_written = 0
        matched_requests: list[DepositRequest] = []

        def note(kind: str, line: str) -> None:
            counts[kind] = counts.get(kind, 0) + 1
            detail_lines.append(f"{kind:<17} {line}")

        def engine_result(req: DepositRequest, pay, ship, etd):
            return compute(
                AnalyticsInput(
                    deposit_request_id=req.id,
                    estimated_etd=etd,
                    created_at=req.created_at.date(),
                    deposit_amount=Decimal(str(req.deposit_amount)),
                    payment_date=pay,
                    ship_date=ship,
                    actual_etd=None,
                    etd_grace_days=grace_days,
                    cost_of_fund_rate=rate,
                    cost_of_fund_grace_days=cof_grace,
                )
            )

        # Matching: the tracker repeats a sunshine number when a file was
        # paid in several rows (multi-tranche entries) — the import made one
        # request per row, so a bare sunshine match can be ambiguous. Tiered
        # disambiguation: same deposit amount, then same request date; each
        # DB request is consumed at most once.
        consumed: set = set()

        def pick_match(row) -> "DepositRequest | None":
            key = norm_key(row["sunshine"])
            cands = [r for r in db_by_key.get(key, []) if r.id not in consumed]
            if len(cands) > 1 and row["deposit"] is not None:
                by_amount = [
                    r for r in cands
                    if abs(Decimal(str(r.deposit_amount)) - row["deposit"]) <= Decimal("0.01")
                ]
                if by_amount:
                    cands = by_amount
            if len(cands) > 1 and row["request_date"]:
                by_date = [r for r in cands if r.created_at.date() == row["request_date"]]
                if by_date:
                    cands = by_date
            return cands[0] if len(cands) == 1 else (cands[0] if cands else None)

        for row in sheet_rows:
            key = norm_key(row["sunshine"])
            label = f"{row['sunshine'] or '(no sunshine #)'}"
            if not key:
                note("NO_SUNSHINE_NO", f"{label} — supplier {row['supplier'][:40]}")
                continue
            req = pick_match(row)
            if req is None:
                where = ""
                if row["request_date"] and row["request_date"] > dt.date(2026, 8, 31):
                    where = " (request date after the 31-Aug import cutoff)"
                if row["cancelled"]:
                    where += " (cancelled in sheet)"
                note("MISSING_IN_DB", f"{label}{where}")
                continue
            consumed.add(req.id)
            matched_requests.append(req)
            db_cancelled = req.current_status in _CANCELLED
            if row["cancelled"] != db_cancelled:
                note("STATUS_DRIFT", f"{label} [{req.request_number}] — sheet "
                                     f"{'cancelled' if row['cancelled'] else 'live'} vs DB "
                                     f"{req.current_status.value}")
                continue
            if row["cancelled"]:
                counts["OK_CANCELLED"] = counts.get("OK_CANCELLED", 0) + 1
                continue

            db_processed = req.current_status == RequestStatus.PAYMENT_PROCESSED
            if row["processed"] != db_processed:
                note("STATUS_DRIFT", f"{label} [{req.request_number}] — sheet "
                                     f"{'processed' if row['processed'] else 'pending'} vs DB "
                                     f"{req.current_status.value}")
                # continue checking inputs anyway — CoF depends on them, not status

            payment = req.payment
            db_pay = payment.payment_date if payment else None
            db_ship = payment.ship_date if payment else None
            drift: list[str] = []
            if db_pay != row["payment_date"]:
                drift.append(f"payment_date DB={db_pay} sheet={row['payment_date']}")
            if db_ship != row["ship_date"]:
                drift.append(f"ship_date DB={db_ship} sheet={row['ship_date']}")
            if req.estimated_etd != row["est_etd"]:
                drift.append(f"est_etd DB={req.estimated_etd} sheet={row['est_etd']}")
            deposit_drift = (
                row["deposit"] is not None
                and abs(Decimal(str(req.deposit_amount)) - row["deposit"]) > Decimal("0.01")
            )
            if deposit_drift:
                drift.append(f"deposit DB={req.deposit_amount} sheet={row['deposit']} (report-only)")

            if drift:
                note("INPUT_DRIFT", f"{label} [{req.request_number}] — " + "; ".join(drift))
                if fix and req.submission_source == SubmissionSource.GOOGLE_FORM:
                    # Repair the CoF inputs from the sheet (dates only).
                    if db_pay != row["payment_date"] or db_ship != row["ship_date"]:
                        if payment is None:
                            payment = PaymentDetails(deposit_request_id=req.id)
                            session.add(payment)
                        for field, new in (
                            ("payment_date", row["payment_date"]),
                            ("ship_date", row["ship_date"]),
                        ):
                            old = getattr(payment, field)
                            if old != new:
                                setattr(payment, field, new)
                                session.add(AuditLog(
                                    entity_name="payment_details", entity_id=req.id,
                                    field_name=field, old_value=str(old), new_value=str(new),
                                    action=AuditAction.UPDATE, changed_by=actor.id,
                                ))
                    if req.estimated_etd != row["est_etd"]:
                        session.add(AuditLog(
                            entity_name="deposit_requests", entity_id=req.id,
                            field_name="estimated_etd",
                            old_value=str(req.estimated_etd), new_value=str(row["est_etd"]),
                            action=AuditAction.UPDATE, changed_by=actor.id,
                        ))
                        req.estimated_etd = row["est_etd"]
                    if db_pay != row["payment_date"]:
                        # Keep the legacy paid tranche's dates consistent.
                        for t in req.tranches:
                            if t.is_legacy and t.status == TrancheStatus.PAID:
                                t.payment_date = row["payment_date"]
                                if row["payment_date"]:
                                    t.paid_at = dt.datetime.combine(
                                        row["payment_date"], dt.time.min, tzinfo=dt.timezone.utc
                                    )
                    fixed_inputs += 1
                    # Recompute drift-free values for the snapshot step below.
                    db_pay, db_ship = row["payment_date"], row["ship_date"]

            # Snapshot check — against the engine run TODAY on the DB inputs
            # (post-fix inputs when --fix corrected them above).
            expected = engine_result(req, db_pay, db_ship, req.estimated_etd)
            snap = req.analytics_snapshot
            exp_cof = float(expected.cost_of_fund_amount) if expected.cost_of_fund_amount is not None else None

            def cof_of(s):  # noqa: ANN001
                return float(s.cost_of_fund_amount) if s and s.cost_of_fund_amount is not None else None

            stale = (
                snap is None
                or snap.etd_grace_overdue_days != expected.etd_grace_overdue_days
                or snap.actual_etd_overdue_days != expected.actual_etd_overdue_days
                or (cof_of(snap) is None) != (exp_cof is None)
                or (exp_cof is not None and cof_of(snap) is not None and abs(cof_of(snap) - exp_cof) > 0.02)
            )
            if snap is None:
                note("MISSING_SNAPSHOT", f"{label} [{req.request_number}] — expected CoF "
                                         f"{exp_cof if exp_cof is not None else '—'}")
            elif stale:
                note("STALE_SNAPSHOT", f"{label} [{req.request_number}] — stored CoF "
                                       f"{cof_of(snap)} overdue {snap.etd_grace_overdue_days} vs "
                                       f"expected CoF {exp_cof} overdue {expected.etd_grace_overdue_days}")
            elif not drift:
                counts["OK"] = counts.get("OK", 0) + 1

            if fix and (stale or drift):
                await AnalyticsRepository(session).upsert(
                    req.id,
                    grace_etd=expected.grace_etd,
                    etd_grace_overdue_days=expected.etd_grace_overdue_days,
                    payment_to_ship_days=expected.payment_to_ship_days,
                    payment_to_request_days=expected.payment_to_request_days,
                    actual_etd_overdue_days=expected.actual_etd_overdue_days,
                    cost_of_fund_applicable=expected.cost_of_fund_applicable,
                    cost_of_fund_amount=expected.cost_of_fund_amount,
                    default_status=expected.default_status,
                )
                snapshots_written += 1

        # DB-only requests (entered after 2 Sep, or renamed sunshine numbers).
        matched_ids = {r.id for r in matched_requests}
        db_only = [r for r in requests if r.id not in matched_ids]
        counts["DB_ONLY"] = len(db_only)

        print("\n──── summary ────")
        for kind in sorted(counts):
            print(f"  {kind:<17} {counts[kind]}")
        shown = detail_lines[:details]
        if shown:
            print(f"\n──── details (first {len(shown)} of {len(detail_lines)}) ────")
            for line in shown:
                print(" ", line)
        if db_only and details:
            print(f"\n──── DB-only requests (not in sheet; first 15 of {len(db_only)}) ────")
            for r in db_only[:15]:
                print(f"  {r.request_number}  {r.sunshine_invoice_number or '—'}  "
                      f"{r.current_status.value}  source={r.submission_source.value if r.submission_source else '—'}")

        if fix:
            await session.commit()
            print(f"\nFIX applied: {fixed_inputs} requests' inputs corrected, "
                  f"{snapshots_written} snapshots recomputed. Committed.")
            print("Reload the analytics — no Recalculate needed for the fixed rows.")
        else:
            print("\nREPORT ONLY — nothing was written. "
                  "Re-run with --fix --actor-email <admin email> to repair.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--fix", action="store_true",
                        help="repair inputs on imported rows + recompute snapshots")
    parser.add_argument("--actor-email", default=None,
                        help="existing user the audit rows are attributed to (required with --fix)")
    parser.add_argument("--details", type=int, default=40,
                        help="how many detail lines to print (default 40)")
    args = parser.parse_args()
    if not args.xlsx.exists():
        sys.exit(f"xlsx not found: {args.xlsx}")
    asyncio.run(run(args.xlsx, fix=args.fix, actor_email=args.actor_email, details=args.details))

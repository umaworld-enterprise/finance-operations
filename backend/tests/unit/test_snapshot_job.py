"""Snapshot job skip rule (4 Sep 2026 fix): a processed+shipped row is only
skipped by the regular (non-force) run when it is TRULY static — it already
has a snapshot AND its graced ETD has passed. Imported rows that arrive
already shipped must get their FIRST snapshot, and rows that shipped within
grace must keep recomputing until the grace date crosses (the 2 Sep CoF gate
flips their Cost of Fund on that day)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.analytics.snapshot_job import _run_snapshots
from app.models.analytics import AnalyticsSnapshot
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus
from app.models.integrations import DefaultedSupplier
from app.models.masters import Customer, Supplier, SystemConfig, User
from app.models.payment import PaymentDetails
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    """_run_snapshots commits (scheduler contract) — wipe what it persisted.
    Also pin the client's 12% CoF rate (the settings default is 18%)."""
    db_session.add(SystemConfig(config_key="cost_of_fund_rate", config_value="0.12"))
    await db_session.flush()
    yield
    for model in (AnalyticsSnapshot, DefaultedSupplier, PaymentDetails,
                  DepositRequest, User, Supplier, Customer, SystemConfig):
        await db_session.execute(delete(model))
    await db_session.commit()


async def _processed_shipped(db_session, ctx, *, etd, ship):
    merch, supplier, customer = ctx
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED, is_locked=True,
        deposit_amount=Decimal("1000.00"),
    )
    req.estimated_etd = etd
    db_session.add(PaymentDetails(
        deposit_request_id=req.id,
        payment_date=etd - timedelta(days=30),
        ship_date=ship,
        payment_status="processed",
    ))
    await db_session.flush()
    return req


async def _snap(db_session, req_id):
    # The job upserts via raw SQL — expire the identity map so the re-read
    # reflects the database, not stale in-session attribute values.
    db_session.expire_all()
    return (
        await db_session.execute(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.deposit_request_id == req_id)
        )
    ).scalar_one_or_none()


async def test_regular_run_computes_first_snapshot_for_imported_shipped_rows(db_session):
    """Processed+shipped WITHOUT a snapshot (the tracker-import state) must be
    picked up by the regular run — previously it was skipped forever."""
    today = date.today()
    ctx = (await make_user(db_session), await make_supplier(db_session), await make_customer(db_session))
    req = await _processed_shipped(
        db_session, ctx,
        etd=today - timedelta(days=60), ship=today - timedelta(days=20),
    )

    count = await _run_snapshots(db_session, force=False)

    assert count >= 1
    snap = await _snap(db_session, req.id)
    assert snap is not None
    # Shipped 40 days after ETD → CoF frozen at ship, charged (grace passed):
    # 1000 × 0.12 × 40 / 365.
    assert snap.actual_etd_overdue_days == 40
    assert float(snap.cost_of_fund_amount) == pytest.approx(1000 * 0.12 * 40 / 365, abs=0.01)


async def test_regular_run_recomputes_shipped_row_until_grace_passes(db_session):
    """A row that shipped WITHIN grace keeps a blank CoF until TODAY crosses
    the grace ETD — so it must not be skipped while grace is still open."""
    today = date.today()
    ctx = (await make_user(db_session), await make_supplier(db_session), await make_customer(db_session))
    # ETD 5 days ago → grace ETD 5 days in the future (grace window open).
    req = await _processed_shipped(
        db_session, ctx,
        etd=today - timedelta(days=5), ship=today - timedelta(days=1),
    )
    # A stale snapshot exists with a bogus value — the run must replace it.
    db_session.add(AnalyticsSnapshot(
        deposit_request_id=req.id, grace_etd=today + timedelta(days=5),
        etd_grace_overdue_days=99, cost_of_fund_amount=Decimal("999.99"),
    ))
    await db_session.flush()

    await _run_snapshots(db_session, force=False)

    snap = await _snap(db_session, req.id)
    assert snap.etd_grace_overdue_days == 0  # shipped → never a defaulter
    # Grace not crossed → nothing charged yet (engine stores 0.00, not NULL).
    assert snap.cost_of_fund_amount is None or float(snap.cost_of_fund_amount) == 0.0


async def test_regular_run_skips_truly_static_shipped_rows(db_session):
    """Processed+shipped WITH a snapshot AND grace already passed is static —
    the regular run leaves it alone (only force recomputes it)."""
    today = date.today()
    ctx = (await make_user(db_session), await make_supplier(db_session), await make_customer(db_session))
    req = await _processed_shipped(
        db_session, ctx,
        etd=today - timedelta(days=60), ship=today - timedelta(days=20),
    )
    db_session.add(AnalyticsSnapshot(
        deposit_request_id=req.id, grace_etd=today - timedelta(days=50),
        etd_grace_overdue_days=0, cost_of_fund_amount=Decimal("123.45"),
    ))
    await db_session.flush()

    await _run_snapshots(db_session, force=False)
    snap = await _snap(db_session, req.id)
    assert float(snap.cost_of_fund_amount) == 123.45  # untouched — skipped

    # force=True (admin Recalculate) recomputes it.
    await _run_snapshots(db_session, force=True)
    snap = await _snap(db_session, req.id)
    assert float(snap.cost_of_fund_amount) == pytest.approx(1000 * 0.12 * 40 / 365, abs=0.01)

"""Weekly Deposit Tracker + all-shipments list (Aug 2026 batch, item 4)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import RequestStatus, TrancheStatus
from app.services.analytics_service import AnalyticsService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _request(db_session, ctx, *, etd=None, status=RequestStatus.PENDING_PAYMENT,
                   tranche_status=TrancheStatus.UNPAID, amount="1000.00", sunshine=None):
    supplier, customer, merch = ctx
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch, status=status,
        deposit_amount=Decimal(amount),
    )
    req.estimated_etd = etd
    if sunshine:
        req.sunshine_invoice_number = sunshine
    await make_tranche(db_session, req, amount=Decimal(amount), status=tranche_status)
    await db_session.flush()
    return req


async def _ctx(db_session):
    return (
        await make_supplier(db_session),
        await make_customer(db_session),
        await make_user(db_session),
    )


# ── Weekly Deposit Tracker ────────────────────────────────────────────────────


async def test_weekly_tracker_buckets_by_etd_week_soonest_first(db_session):
    ctx = await _ctx(db_session)
    # Two different ISO weeks + one request with no ETD.
    week1 = await _request(db_session, ctx, etd=date(2026, 8, 5), amount="500.00")   # Wed, wk of 3 Aug
    week2 = await _request(db_session, ctx, etd=date(2026, 8, 12), amount="700.00")  # Wed, wk of 10 Aug
    no_etd = await _request(db_session, ctx, etd=None, amount="900.00")

    groups = await AnalyticsService(db_session).get_weekly_deposit_tracker()

    assert [g["week_start"] for g in groups] == ["2026-08-03", "2026-08-10", None]
    assert groups[0]["week"] == "03-Aug-2026 to 09-Aug-2026"
    assert groups[0]["rows"][0]["request_number"] == week1.request_number
    assert groups[0]["outstanding"] == {"USD": 500.0}
    assert groups[1]["rows"][0]["request_number"] == week2.request_number
    assert groups[2]["week"] == "No ETD recorded"
    assert groups[2]["rows"][0]["request_number"] == no_etd.request_number


async def test_weekly_tracker_only_unpaid_live_deposits(db_session):
    ctx = await _ctx(db_session)
    kept = await _request(db_session, ctx, etd=date(2026, 8, 5))
    await _request(db_session, ctx, etd=date(2026, 8, 5), tranche_status=TrancheStatus.PAID)
    await _request(
        db_session, ctx, etd=date(2026, 8, 5), status=RequestStatus.CANCELLED_BY_ACCOUNTS
    )

    groups = await AnalyticsService(db_session).get_weekly_deposit_tracker()

    assert len(groups) == 1
    assert [r["request_number"] for r in groups[0]["rows"]] == [kept.request_number]


# ── All-shipments list ────────────────────────────────────────────────────────


async def test_shipments_days_delayed_against_today_most_delayed_first(db_session):
    ctx = await _ctx(db_session)
    today = date.today()
    overdue_10 = await _request(db_session, ctx, etd=today - timedelta(days=10))
    overdue_3 = await _request(db_session, ctx, etd=today - timedelta(days=3))
    future = await _request(db_session, ctx, etd=today + timedelta(days=5))
    no_etd = await _request(db_session, ctx, etd=None)

    rows = await AnalyticsService(db_session).get_shipments_list()

    assert [r["request_number"] for r in rows] == [
        overdue_10.request_number,
        overdue_3.request_number,
        future.request_number,
        no_etd.request_number,
    ]
    assert rows[0]["days_delayed"] == 10
    assert rows[1]["days_delayed"] == 3
    assert rows[2]["days_delayed"] == 0  # future ETD is floored, never negative
    assert rows[3]["days_delayed"] is None


async def test_shipments_include_identifiers_and_exclude_cancelled(db_session):
    ctx = await _ctx(db_session)
    kept = await _request(
        db_session, ctx, etd=date(2026, 8, 5), sunshine="INV-42", amount="1234.00"
    )
    await _request(
        db_session, ctx, etd=date(2026, 8, 5), status=RequestStatus.REJECTED_BY_HOM
    )

    rows = await AnalyticsService(db_session).get_shipments_list()

    assert len(rows) == 1
    row = rows[0]
    assert row["request_number"] == kept.request_number
    assert row["sunshine_invoice_number"] == "INV-42"
    assert row["amount"] == 1234.0
    assert row["current_status"] == "pending_payment"

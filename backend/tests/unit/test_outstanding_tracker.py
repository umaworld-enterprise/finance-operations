"""Outstanding Deposit Tracker — tranche-level outstanding, all groupings."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.enums import CurrencyCode, RequestStatus, TrancheStatus, UserRole
from app.services.analytics_service import AnalyticsService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
    make_vertical,
)

pytestmark = pytest.mark.asyncio


async def _seed(db_session):
    """Two merchandisers, two customers/verticals, mixed paid/unpaid tranches
    across two ISO weeks and two currencies."""
    m1 = await make_user(db_session, UserRole.MERCHANDISER)
    m2 = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    c1 = await make_customer(db_session)
    c2 = await make_customer(db_session)
    v1 = await make_vertical(db_session)
    v2 = await make_vertical(db_session)

    # Monday 2026-07-06 and Monday 2026-07-13 (distinct ISO weeks)
    wk1 = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
    wk2 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)

    # r1: USD, week 1, m1/c1/v1 — 600 unpaid + 400 paid (partial payment)
    r1 = await make_request(
        db_session, supplier=supplier, customer=c1, created_by=m1, vertical=v1,
        currency=CurrencyCode.USD, created_at=wk1,
    )
    await make_tranche(db_session, r1, number=1, amount=Decimal("600.00"))
    await make_tranche(
        db_session, r1, number=2, amount=Decimal("400.00"), status=TrancheStatus.PAID
    )

    # r2: CNY, week 2, m2/c2/v2 — 1000 unpaid
    r2 = await make_request(
        db_session, supplier=supplier, customer=c2, created_by=m2, vertical=v2,
        currency=CurrencyCode.CNY, created_at=wk2,
    )
    await make_tranche(db_session, r2, number=1, amount=Decimal("1000.00"))

    # r3: cancelled request — its unpaid tranche must NOT count
    r3 = await make_request(
        db_session, supplier=supplier, customer=c1, created_by=m1, vertical=v1,
        currency=CurrencyCode.USD, created_at=wk1,
        status=RequestStatus.CANCELLED_BY_MERCHANDISER,
    )
    await make_tranche(db_session, r3, number=1, amount=Decimal("9999.00"))

    return m1, m2, c1, c2, v1, v2


async def test_outstanding_excludes_paid_and_cancelled(db_session):
    await _seed(db_session)
    svc = AnalyticsService(db_session)
    rows = await svc.get_outstanding_tracker("merchandiser")
    total_usd = sum(r["outstanding"].get("USD", 0) for r in rows)
    total_cny = sum(r["outstanding"].get("CNY", 0) for r in rows)
    assert total_usd == 600.0  # paid 400 and cancelled 9999 excluded
    assert total_cny == 1000.0


async def test_group_by_merchandiser(db_session):
    m1, m2, *_ = await _seed(db_session)
    svc = AnalyticsService(db_session)
    rows = await svc.get_outstanding_tracker("merchandiser")
    by_name = {r["group"]: r for r in rows}
    assert by_name[m1.full_name]["outstanding"] == {"USD": 600.0}
    assert by_name[m1.full_name]["tranche_count"] == 1
    assert by_name[m2.full_name]["outstanding"] == {"CNY": 1000.0}


async def test_group_by_customer_and_vertical(db_session):
    _, _, c1, c2, v1, v2 = await _seed(db_session)
    svc = AnalyticsService(db_session)

    by_customer = {r["group"]: r for r in await svc.get_outstanding_tracker("customer")}
    assert by_customer[c1.name]["outstanding"] == {"USD": 600.0}
    assert by_customer[c2.name]["outstanding"] == {"CNY": 1000.0}

    by_vertical = {r["group"]: r for r in await svc.get_outstanding_tracker("vertical")}
    assert by_vertical[v1.name]["outstanding"] == {"USD": 600.0}
    assert by_vertical[v2.name]["outstanding"] == {"CNY": 1000.0}


async def test_group_by_week_uses_request_created_date(db_session):
    await _seed(db_session)
    svc = AnalyticsService(db_session)
    rows = await svc.get_outstanding_tracker("week")
    # Newest week first, with explicit Monday–Sunday boundaries.
    assert [r["group"] for r in rows] == [
        "13-Jul-2026 to 19-Jul-2026",
        "06-Jul-2026 to 12-Jul-2026",
    ]
    assert rows[0]["outstanding"] == {"CNY": 1000.0}
    assert rows[1]["outstanding"] == {"USD": 600.0}


async def test_date_range_filter(db_session):
    await _seed(db_session)
    svc = AnalyticsService(db_session)
    from datetime import date

    rows = await svc.get_outstanding_tracker(
        "week", date_from=date(2026, 7, 13), date_to=date(2026, 7, 19)
    )
    assert len(rows) == 1
    assert rows[0]["outstanding"] == {"CNY": 1000.0}

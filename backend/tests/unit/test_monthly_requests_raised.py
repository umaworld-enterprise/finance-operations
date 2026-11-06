"""Requests raised per month in one currency, with a 3-month average
(5 Nov 2026, executive request)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.enums import CurrencyCode, RequestStatus, UserRole
from app.services.analytics_service import AnalyticsService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _raised(db_session, *, amount, currency=CurrencyCode.USD, months_ago=0,
                  status=RequestStatus.PENDING_PAYMENT):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=currency, deposit_amount=Decimal(amount), status=status,
    )
    when = datetime.now(timezone.utc) - timedelta(days=31 * months_ago)
    req.created_at = when
    await db_session.flush()
    return req


async def test_current_month_total_and_contiguous_series(db_session):
    await _raised(db_session, amount="1000.00")
    await _raised(db_session, amount="500.00")

    series = await AnalyticsService(db_session).get_monthly_requests_raised(months=6)
    assert len(series) == 6                      # contiguous, empty months included
    assert series[-1]["total"] == 1500.0
    assert series[-1]["requests"] == 2
    assert series[0]["total"] == 0.0


async def test_other_currencies_are_not_mixed_in(db_session):
    await _raised(db_session, amount="1000.00", currency=CurrencyCode.USD)
    await _raised(db_session, amount="9999.00", currency=CurrencyCode.EUR)

    series = await AnalyticsService(db_session).get_monthly_requests_raised(currency="USD", months=3)
    assert series[-1]["total"] == 1000.0


async def test_cancelled_and_rejected_do_not_count_as_raised(db_session):
    await _raised(db_session, amount="1000.00")
    await _raised(db_session, amount="800.00", status=RequestStatus.CANCELLED_BY_MERCHANDISER)
    await _raised(db_session, amount="700.00", status=RequestStatus.REJECTED_BY_ACCOUNTS)

    series = await AnalyticsService(db_session).get_monthly_requests_raised(months=3)
    assert series[-1]["total"] == 1000.0


async def test_three_month_average_waits_for_three_months(db_session):
    await _raised(db_session, amount="300.00")
    series = await AnalyticsService(db_session).get_monthly_requests_raised(months=4)

    # A partial window would read as a dip that never happened.
    assert series[0]["avg_3m"] is None
    assert series[1]["avg_3m"] is None
    assert series[2]["avg_3m"] is not None
    assert series[-1]["avg_3m"] == round(300.0 / 3, 2)


async def test_month_over_month_change_is_reported(db_session):
    series = await AnalyticsService(db_session).get_monthly_requests_raised(months=3)
    assert series[0]["mom_change"] is None       # nothing to compare the first month to
    assert all("mom_pct" in p for p in series)

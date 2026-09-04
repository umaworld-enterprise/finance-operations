"""By Merchandiser / By Vertical / By Customer analytics tables (4 Sep 2026):
regression coverage after the client reported the tabs coming up empty, plus
the per-currency Notional Gain (= Cost of Fund) columns from the new sheet."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.analytics import AnalyticsSnapshot
from app.models.enums import CurrencyCode
from app.services.analytics_service import AnalyticsService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_user,
    make_vertical,
)

pytestmark = pytest.mark.asyncio


async def _snapshot(db_session, request, *, overdue_days, cof, grace_etd=None,
                    actual_overdue=None):
    db_session.add(
        AnalyticsSnapshot(
            deposit_request_id=request.id,
            grace_etd=grace_etd,
            etd_grace_overdue_days=overdue_days,
            actual_etd_overdue_days=actual_overdue,
            cost_of_fund_applicable=cof is not None,
            cost_of_fund_amount=cof,
        )
    )
    await db_session.flush()


async def _delayed_request(db_session, *, merch, supplier, customer, vertical=None,
                           currency=CurrencyCode.USD, amount="1000.00",
                           overdue_days=20, cof="50.00"):
    today = date.today()
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        vertical=vertical, currency=currency, deposit_amount=Decimal(amount),
    )
    req.estimated_etd = today - timedelta(days=overdue_days + 10)
    await _snapshot(
        db_session, req,
        overdue_days=overdue_days,
        cof=Decimal(cof) if cof is not None else None,
        grace_etd=req.estimated_etd + timedelta(days=10),
        actual_overdue=overdue_days + 10,
    )
    return req


async def test_by_merchandiser_populates_with_per_currency_notional(db_session):
    """One delayed row must produce a table row (the reported bug was empty
    tabs), and the Notional/CoF columns split per currency over ALL live rows
    of the merchandiser — not just the delayed ones."""
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    await _delayed_request(
        db_session, merch=merch, supplier=supplier, customer=customer,
        currency=CurrencyCode.USD, amount="1000.00", cof="50.00",
    )
    # A NON-delayed row of the same merchandiser in CNY: contributes to
    # notional_cny but not to the overdue case count.
    quiet = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=CurrencyCode.CNY, deposit_amount=Decimal("2000.00"),
    )
    await _snapshot(db_session, quiet, overdue_days=0, cof=Decimal("7.25"))

    rows = await AnalyticsService(db_session).get_by_merchandiser()

    assert len(rows) == 1
    row = rows[0]
    assert row["merchandiser"] == merch.full_name
    assert row["overdue_cases"] == 1
    assert row["overdue_usd"] == 1000.0
    assert row["overdue_cny"] == 0.0
    assert row["contribution_pct"] == 100.0
    assert row["notional_usd"] == 50.0
    assert row["notional_cny"] == 7.25
    assert row["notional_eur"] == 0.0
    # Backward-compatible USD alias.
    assert row["notional_gain"] == 50.0


async def test_by_vertical_populates_with_per_currency_notional(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    vertical = await make_vertical(db_session)

    await _delayed_request(
        db_session, merch=merch, supplier=supplier, customer=customer,
        vertical=vertical, currency=CurrencyCode.EUR, amount="400.00", cof="12.00",
    )

    rows = await AnalyticsService(db_session).get_by_vertical()

    assert len(rows) == 1
    row = rows[0]
    assert row["category"] == vertical.name
    assert row["overdue_cases"] == 1
    assert row["overdue_eur"] == 400.0
    assert row["notional_eur"] == 12.0
    assert row["notional_usd"] == 0.0


async def test_by_customer_populates_with_per_currency_notional(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    await _delayed_request(
        db_session, merch=merch, supplier=supplier, customer=customer,
        currency=CurrencyCode.USD, amount="900.00", cof="33.00",
    )

    rows = await AnalyticsService(db_session).get_by_customer()

    assert len(rows) == 1
    row = rows[0]
    assert row["customer"] == customer.name
    assert row["overdue_cases"] == 1
    assert row["overdue_usd"] == 900.0
    assert row["notional_usd"] == 33.0
    assert row["notional_gain"] == 33.0


async def test_grouped_tables_show_nothing_without_delayed_snapshots(db_session):
    """Rows exist but none are Delayed (overdue 0 / no snapshot) → the tables
    are legitimately empty. This is the state a stale-snapshot server is in —
    the fix is Recalculate, not a query change."""
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
    )
    await _snapshot(db_session, req, overdue_days=0, cof=None)
    # And one request with NO snapshot at all (never recalculated).
    await make_request(db_session, supplier=supplier, customer=customer, created_by=merch)

    svc = AnalyticsService(db_session)
    assert await svc.get_by_merchandiser() == []
    assert await svc.get_by_vertical() == []
    assert await svc.get_by_customer() == []

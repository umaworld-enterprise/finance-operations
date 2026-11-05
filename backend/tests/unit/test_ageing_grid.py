"""Ageing tab (5 Nov 2026, executive request): deposit value aged into
15-day bands as a currency matrix, cut either by band or by customer.

Two bases share the grid:
  shipment — money already PAID OUT against goods that have not shipped,
             aged from the original Est ETD (the Delay Buckets population).
  payment  — money we still OWE: unpaid tranches aged from their tentative
             payment date.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.analytics import AnalyticsSnapshot
from app.models.enums import CurrencyCode, RequestStatus, TrancheStatus, UserRole
from app.models.payment import PaymentDetails
from app.services.analytics_service import AnalyticsService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio

TODAY = date.today()


async def _paid_unshipped(db_session, *, customer, etd_days_ago, amount, currency):
    """A deposit paid out whose goods have not shipped and whose ETD passed."""
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=currency, deposit_amount=Decimal(amount),
        status=RequestStatus.PAYMENT_PROCESSED,
    )
    req.estimated_etd = TODAY - timedelta(days=etd_days_ago)
    db_session.add(AnalyticsSnapshot(deposit_request_id=req.id, etd_grace_overdue_days=etd_days_ago))
    db_session.add(
        PaymentDetails(
            deposit_request_id=req.id,
            payment_date=TODAY - timedelta(days=etd_days_ago + 20),
            ship_date=None,
        )
    )
    await db_session.flush()
    return req


def _row(grid, label):
    return next((r for r in grid["rows"] if r["label"] == label), None)


# ── Shipment basis ───────────────────────────────────────────────────────────


async def test_shipment_basis_ages_into_the_right_band_and_currency(db_session):
    cust = await make_customer(db_session)
    await _paid_unshipped(db_session, customer=cust, etd_days_ago=20, amount="1000.00",
                          currency=CurrencyCode.USD)
    await _paid_unshipped(db_session, customer=cust, etd_days_ago=50, amount="700.00",
                          currency=CurrencyCode.EUR)

    grid = await AnalyticsService(db_session).get_ageing(basis="shipment", cut="currency")

    assert _row(grid, "15-30 Days")["amounts"]["USD"] == 1000.0
    assert _row(grid, "45-60 Days")["amounts"]["EUR"] == 700.0
    # Column totals are per currency — never summed across them.
    assert grid["totals"]["USD"] == 1000.0
    assert grid["totals"]["EUR"] == 700.0


async def test_shipment_basis_excludes_shipped_and_unpaid_rows(db_session):
    """Same population rule as the Delay Buckets tab, so the two reconcile."""
    cust = await make_customer(db_session)
    shipped = await _paid_unshipped(db_session, customer=cust, etd_days_ago=20,
                                    amount="500.00", currency=CurrencyCode.USD)
    payment = (await db_session.execute(
        select(PaymentDetails).where(PaymentDetails.deposit_request_id == shipped.id)
    )).scalar_one()
    payment.ship_date = TODAY           # it shipped → no longer ageing
    await db_session.flush()

    grid = await AnalyticsService(db_session).get_ageing(basis="shipment", cut="currency")
    assert grid["totals"] == {} or all(v == 0 for v in grid["totals"].values())


async def test_shipment_basis_ignores_requests_whose_etd_has_not_passed(db_session):
    cust = await make_customer(db_session)
    await _paid_unshipped(db_session, customer=cust, etd_days_ago=-5, amount="900.00",
                          currency=CurrencyCode.USD)

    grid = await AnalyticsService(db_session).get_ageing(basis="shipment", cut="currency")
    assert all(v == 0 for v in grid["totals"].values()) or grid["totals"] == {}


# ── Payment basis ────────────────────────────────────────────────────────────


async def _with_unpaid_tranche(db_session, *, customer, due_days_ago, amount, currency):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=currency, status=RequestStatus.PENDING_PAYMENT,
    )
    t = await make_tranche(db_session, req, amount=Decimal(amount))
    t.status = TrancheStatus.UNPAID
    t.tentative_payment_date = TODAY - timedelta(days=due_days_ago)
    await db_session.flush()
    return req


async def test_payment_basis_ages_unpaid_tranches(db_session):
    cust = await make_customer(db_session)
    await _with_unpaid_tranche(db_session, customer=cust, due_days_ago=40,
                               amount="300.00", currency=CurrencyCode.USD)

    grid = await AnalyticsService(db_session).get_ageing(basis="payment", cut="currency")
    assert _row(grid, "30-45 Days")["amounts"]["USD"] == 300.0


async def test_payment_basis_separates_not_yet_due(db_session):
    cust = await make_customer(db_session)
    await _with_unpaid_tranche(db_session, customer=cust, due_days_ago=-10,
                               amount="250.00", currency=CurrencyCode.USD)

    grid = await AnalyticsService(db_session).get_ageing(basis="payment", cut="currency")
    assert _row(grid, "Not yet due")["amounts"]["USD"] == 250.0
    assert grid["rows"][0]["label"] == "Not yet due"   # sits at the top of the ladder


# ── Customer cut ─────────────────────────────────────────────────────────────


async def test_customer_cut_puts_customers_on_the_left(db_session):
    a = await make_customer(db_session)
    b = await make_customer(db_session)
    await _paid_unshipped(db_session, customer=a, etd_days_ago=20, amount="1000.00",
                          currency=CurrencyCode.USD)
    await _paid_unshipped(db_session, customer=b, etd_days_ago=80, amount="400.00",
                          currency=CurrencyCode.CNY)

    grid = await AnalyticsService(db_session).get_ageing(basis="shipment", cut="customer")
    labels = [r["label"] for r in grid["rows"]]
    assert a.name in labels and b.name in labels
    assert _row(grid, a.name)["amounts"]["USD"] == 1000.0
    assert _row(grid, b.name)["amounts"]["CNY"] == 400.0
    # A customer's own row carries zero in the currencies it has no value in.
    assert _row(grid, a.name)["amounts"]["CNY"] == 0.0
    assert grid["totals"]["USD"] == 1000.0
    assert grid["totals"]["CNY"] == 400.0


async def test_customer_cut_omits_customers_with_nothing_outstanding(db_session):
    a = await make_customer(db_session)
    await make_customer(db_session)          # never used — must not appear
    await _paid_unshipped(db_session, customer=a, etd_days_ago=20, amount="100.00",
                          currency=CurrencyCode.USD)

    grid = await AnalyticsService(db_session).get_ageing(basis="shipment", cut="customer")
    assert [r["label"] for r in grid["rows"]] == [a.name]

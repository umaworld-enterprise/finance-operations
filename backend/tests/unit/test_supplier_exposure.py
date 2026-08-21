"""Supplier live-exposure endpoint (UAT change note Aug 2026, item 2):
open requests split by graced-ETD passed vs not yet passed, excluding
closed (cancelled/rejected) and already-shipped files."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.v1.masters.suppliers import get_supplier_exposure
from app.models.analytics import AnalyticsSnapshot
from app.models.enums import RequestStatus
from app.models.payment import PaymentDetails
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _snapshot(db_session, request, grace_etd, overdue=None):
    snap = AnalyticsSnapshot(
        id=uuid.uuid4(),
        deposit_request_id=request.id,
        grace_etd=grace_etd,
        etd_grace_overdue_days=overdue,
    )
    db_session.add(snap)
    await db_session.flush()
    return snap


async def test_exposure_buckets_and_exclusions(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    today = date.today()

    # 1. Graced ETD passed — counts in the "passed" bucket.
    overdue_req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED, deposit_amount=Decimal("500.00"),
    )
    overdue_req.sunshine_invoice_number = "SUN-2026-042"
    await db_session.flush()
    await _snapshot(db_session, overdue_req, today - timedelta(days=5), overdue=5)

    # 2. Graced ETD in the future — "pending" bucket.
    pending_req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT, deposit_amount=Decimal("300.00"),
    )
    await _snapshot(db_session, pending_req, today + timedelta(days=10))

    # 3. No snapshot at all — still exposure, lands in "pending".
    bare_req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT, deposit_amount=Decimal("200.00"),
    )

    # 4. Cancelled — excluded entirely.
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.CANCELLED_BY_MERCHANDISER, deposit_amount=Decimal("999.00"),
    )
    # 5. Rejected by accounts — excluded entirely.
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.REJECTED_BY_ACCOUNTS, deposit_amount=Decimal("888.00"),
    )

    # 6. Shipped — goods delivered, exposure over, excluded.
    shipped_req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED, deposit_amount=Decimal("777.00"),
    )
    db_session.add(
        PaymentDetails(
            id=uuid.uuid4(),
            deposit_request_id=shipped_req.id,
            ship_date=today - timedelta(days=1),
        )
    )
    await db_session.flush()

    # 7. Another supplier's request — not included.
    other_supplier = await make_supplier(db_session)
    await make_request(
        db_session, supplier=other_supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT, deposit_amount=Decimal("111.00"),
    )

    result = await get_supplier_exposure(supplier.id, db_session, None)

    assert [r.request_number for r in result.graced_etd_passed] == [overdue_req.request_number]
    assert result.graced_etd_passed[0].etd_grace_overdue_days == 5
    # Overdue rows carry the Sunshine Invoice No. (19 Aug 2026).
    assert result.graced_etd_passed[0].sunshine_invoice_number == "SUN-2026-042"
    assert {r.request_number for r in result.graced_etd_pending} == {
        pending_req.request_number, bare_req.request_number,
    }
    # 500 + 300 + 200, all USD (factory default) — shipped/cancelled/rejected
    # amounts never appear.
    assert result.totals_by_currency == {"USD": Decimal("1000.00")}


async def test_exposure_empty_for_clean_supplier(db_session):
    supplier = await make_supplier(db_session)
    result = await get_supplier_exposure(supplier.id, db_session, None)
    assert result.graced_etd_passed == []
    assert result.graced_etd_pending == []
    assert result.totals_by_currency == {}

"""FY-to-date payment-queue KPIs (UAT change note Aug 2026, items 5/17/19):
counts grouped into the six dashboard buckets, windowed to the current
April–March financial year by created date."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import RequestStatus
from app.services.deposit_request_service import DepositRequestService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


def _fy_start() -> datetime:
    """Same rule the service applies: FY starts 1 April (April–March)."""
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 4 else now.year - 1
    return datetime(year, 4, 1, tzinfo=timezone.utc)


async def test_kpis_bucket_by_status_within_the_financial_year(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    in_fy = _fy_start() + timedelta(days=1)

    statuses = [
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.PENDING_HOM_APPROVAL,
        RequestStatus.HOLD_BY_MERCHANDISER,
        RequestStatus.HOLD_BY_ACCOUNTS,
        RequestStatus.PAYMENT_PROCESSED,
        RequestStatus.REJECTED_BY_ACCOUNTS,
        RequestStatus.REJECTED_BY_HOM,
        RequestStatus.CANCELLED_BY_MERCHANDISER,
        RequestStatus.CANCELLED_BY_ACCOUNTS,
    ]
    for status in statuses:
        await make_request(
            db_session, supplier=supplier, customer=customer, created_by=merch,
            status=status, created_at=in_fy,
        )

    kpis = await DepositRequestService(db_session).get_queue_kpis()
    assert kpis["pending_payment"] == 2
    assert kpis["awaiting_hom"] == 1
    assert kpis["on_hold"] == 2  # both hold sides
    assert kpis["processed"] == 1
    assert kpis["rejected"] == 2  # by accounts + by HoM
    assert kpis["cancelled"] == 2  # by merchandiser + by accounts
    assert kpis["total"] == 10
    assert kpis["fy_start"] == _fy_start().date().isoformat()
    assert kpis["fy_label"].startswith("FY ")


async def test_kpis_exclude_requests_created_before_the_fy(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED,
        created_at=_fy_start() - timedelta(days=10),  # last FY
    )
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED,
        created_at=_fy_start() + timedelta(days=10),  # this FY
    )

    kpis = await DepositRequestService(db_session).get_queue_kpis()
    assert kpis["processed"] == 1
    assert kpis["total"] == 1

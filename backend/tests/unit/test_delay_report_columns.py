"""Delay Report columns (29 Sep 2026, executive request): the report must
carry the Sunshine Invoice No. (how the team identifies a file) and the
Original ETD (the date the Grace ETD is derived from) alongside the existing
overdue figures.
"""

import csv
import io
from datetime import date, timedelta

import pytest

from app.models.analytics import AnalyticsSnapshot
from app.models.enums import RequestStatus, UserRole
from app.services.report_service import ReportService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


def _parse_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


async def _overdue_request(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED,
    )
    request.sunshine_invoice_number = "AGV-2026-501"
    request.estimated_etd = date(2026, 4, 27)
    await db_session.flush()

    db_session.add(
        AnalyticsSnapshot(
            deposit_request_id=request.id,
            grace_etd=request.estimated_etd + timedelta(days=10),
            etd_grace_overdue_days=12,
            payment_to_ship_days=None,
            default_status="delayed",
        )
    )
    await db_session.flush()
    return request


async def test_delay_report_includes_sunshine_invoice_and_original_etd(db_session):
    request = await _overdue_request(db_session)

    data, content_type = await ReportService(db_session).delay_report("csv")
    assert "csv" in content_type
    rows = _parse_csv(data)

    header_row = next(r for r in rows if "Request #" in r)
    assert "Sunshine Invoice No." in header_row
    assert "Original ETD" in header_row
    # The pre-existing columns must survive the addition.
    for existing in ("Supplier", "Customer", "Grace ETD", "ETD Grace Overdue Days", "Status"):
        assert existing in header_row

    data_row = next(r for r in rows if request.request_number in r)
    assert data_row[header_row.index("Sunshine Invoice No.")] == "AGV-2026-501"
    assert "2026-04-27" in data_row[header_row.index("Original ETD")]


async def test_delay_report_renders_in_every_format(db_session):
    """Column count changed — the Excel and PDF builders must still render."""
    await _overdue_request(db_session)
    svc = ReportService(db_session)
    for fmt in ("csv", "excel", "pdf"):
        data, _content_type = await svc.delay_report(fmt)
        assert data, f"{fmt} produced no bytes"

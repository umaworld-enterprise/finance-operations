"""Pending Payments + Ageing report extracts (5 Nov 2026).

Two client complaints drive these: exports arriving as text rather than
numbers, and the Pending extract ageing off the FILE's request date when the
team needs the tranche's own dates.
"""

import io
from datetime import date, timedelta
from decimal import Decimal

import openpyxl
import pytest

from app.models.analytics import AnalyticsSnapshot
from app.models.enums import CurrencyCode, RequestStatus, TrancheStatus, UserRole
from app.models.payment import PaymentDetails
from app.services.report_service import ReportService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio
TODAY = date.today()


async def _pending_with_tranches(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=CurrencyCode.USD, status=RequestStatus.PENDING_PAYMENT,
    )
    t1 = await make_tranche(db_session, req, number=1, amount=Decimal("600.00"))
    t1.status = TrancheStatus.UNPAID
    t1.tentative_payment_date = TODAY - timedelta(days=20)
    t2 = await make_tranche(db_session, req, number=2, amount=Decimal("400.00"))
    t2.status = TrancheStatus.UNPAID
    t2.tentative_payment_date = TODAY - timedelta(days=5)
    await db_session.flush()
    return req


def _sheet(data: bytes):
    return openpyxl.load_workbook(io.BytesIO(data)).active


async def test_amounts_and_dates_are_real_excel_types(db_session):
    """The reported defect: 'even numbers are not identified as Numbers'."""
    await _pending_with_tranches(db_session)
    data, ctype = await ReportService(db_session).pending_payments_report("excel")
    assert "spreadsheet" in ctype
    ws = _sheet(data)

    headers = [c.value for c in ws[1]]
    row = {h: c.value for h, c in zip(headers, ws[2])}

    assert isinstance(row["Deposit Amount"], (int, float))
    assert isinstance(row["Amount Payable"], (int, float))
    assert isinstance(row["Days Waiting"], int)
    assert hasattr(row["Request Date"], "year")          # a real date, not text
    assert hasattr(row["Tentative Payment"], "year")


async def test_header_is_styled_and_frozen(db_session):
    await _pending_with_tranches(db_session)
    data, _ = await ReportService(db_session).pending_payments_report("excel")
    ws = _sheet(data)

    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None
    assert ws["A1"].font.bold is True
    assert ws["A1"].fill.start_color.rgb.endswith("1F4E79")
    assert ws.column_dimensions["A"].width >= 10


async def test_tranche_column_lists_each_tranche_with_its_own_date(db_session):
    """Ageing must key off the tranche, not the file — so every unpaid
    tranche is named with its own date, one per line."""
    await _pending_with_tranches(db_session)
    data, _ = await ReportService(db_session).pending_payments_report("excel")
    ws = _sheet(data)
    headers = [c.value for c in ws[1]]
    cell = ws.cell(row=2, column=headers.index("Tranches (raised date)") + 1).value

    lines = cell.split("\n")
    assert len(lines) == 2
    # The app's own tranche label is used verbatim (e.g. "Deposit - Tranche 1").
    assert "Tranche 1" in lines[0] and "Tranche 2" in lines[1]
    assert (TODAY - timedelta(days=20)).strftime("%d-%b-%y") in lines[0]
    assert (TODAY - timedelta(days=5)).strftime("%d-%b-%y") in lines[1]


async def test_delay_band_comes_from_the_earliest_tranche_due_date(db_session):
    await _pending_with_tranches(db_session)
    data, _ = await ReportService(db_session).pending_payments_report("excel")
    ws = _sheet(data)
    headers = [c.value for c in ws[1]]
    row = {h: c.value for h, c in zip(headers, ws[2])}
    # Earliest unpaid tranche is 20 days overdue.
    assert row["Days Waiting"] == 20
    assert row["Payment Delay"] == "15-30 Days"


async def test_pending_report_carries_the_tab_columns(db_session):
    await _pending_with_tranches(db_session)
    data, _ = await ReportService(db_session).pending_payments_report("excel")
    headers = [c.value for c in _sheet(data)[1]]
    for expected in (
        "Request #", "Request Date", "Sunshine Invoice No.", "Supplier",
        "Supplier Proforma Invoice No.", "Vertical/Category", "Customer",
        "Merchandiser", "Currency", "Amount Payable", "Deposit %",
        "Deposit Amount", "Tentative Payment", "Priority",
    ):
        assert expected in headers, f"missing column: {expected}"


# ── Ageing extract ───────────────────────────────────────────────────────────


async def test_ageing_report_matches_the_grid_and_totals(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=CurrencyCode.USD, deposit_amount=Decimal("1000.00"),
        status=RequestStatus.PAYMENT_PROCESSED,
    )
    req.estimated_etd = TODAY - timedelta(days=20)
    db_session.add(AnalyticsSnapshot(deposit_request_id=req.id, etd_grace_overdue_days=20))
    db_session.add(PaymentDetails(
        deposit_request_id=req.id, payment_date=TODAY - timedelta(days=40), ship_date=None,
    ))
    await db_session.flush()

    data, _ = await ReportService(db_session).ageing_report("excel", basis="shipment", cut="currency")
    ws = _sheet(data)
    headers = [c.value for c in ws[1]]
    assert headers[0] == "Delay Bucket"
    assert "USD" in headers

    body = {r[0].value: r for r in ws.iter_rows(min_row=2)}
    usd = headers.index("USD")
    assert body["15-30 Days"][usd].value == 1000.0
    assert body["Total"][usd].value == 1000.0          # totals travel with the sheet

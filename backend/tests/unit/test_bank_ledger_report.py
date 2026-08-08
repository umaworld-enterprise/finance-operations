"""Bank Ledger report (UAT change note Aug 2026, item 1): the exact columns
Accounts paste into the bank ledger sheet — Supplier, Supplier Proforma
Invoice No., Sunshine Invoice No., Selected Customer, Currency, Deposit
Amount."""

import csv
import io
from decimal import Decimal

import pytest

from app.models.enums import RequestStatus, UserRole
from app.services.report_service import ReportService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio

_HEADERS = [
    "Supplier", "Supplier Proforma Invoice No.", "Sunshine Invoice No.",
    "Selected Customer", "Currency", "Deposit Amount",
]


def _parse_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


async def test_bank_ledger_columns_and_rows(db_session):
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=accounts,
        deposit_amount=Decimal("1234.56"),
    )
    request.supplier_invoice_number = "PF-77"
    request.sunshine_invoice_number = "AGV-77"
    await db_session.flush()

    data, content_type = await ReportService(db_session).bank_ledger_report(
        UserRole.ACCOUNTS_TEAM, accounts.id, "csv"
    )
    assert "csv" in content_type
    rows = _parse_csv(data)
    # First data row after any title/header rows must carry our values in
    # the exact column order.
    header_idx = next(i for i, row in enumerate(rows) if row[:1] == ["Supplier"])
    assert rows[header_idx] == _HEADERS
    body = rows[header_idx + 1]
    assert body[0] == supplier.name
    assert body[1] == "PF-77"
    assert body[2] == "AGV-77"
    assert body[3] == customer.name
    assert body[4] == "USD"
    assert Decimal(body[5]) == Decimal("1234.56")


async def test_bank_ledger_scopes_merchandisers_to_their_own(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    mine = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED,
    )
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=other,
    )

    data, _ = await ReportService(db_session).bank_ledger_report(
        UserRole.MERCHANDISER, merch.id, "csv"
    )
    text = data.decode("utf-8-sig")
    assert mine.request_number not in text  # request # is deliberately not a column
    # Exactly one data row: header + 1 (allow for a title line).
    rows = [r for r in _parse_csv(data) if r and r[0] == supplier.name]
    assert len(rows) == 1

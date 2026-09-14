"""Invoice-number edits on closed requests (9 Sep 2026): Accounts / Super
Admin may correct the Sunshine & Supplier Proforma invoice numbers at ANY
status — completion lock included — while every other field keeps the
existing lock rules."""

from decimal import Decimal

import pytest

from app.core.exceptions import RecordLockedError
from app.models.enums import RequestStatus, UserRole
from app.schemas.deposit_request import DepositRequestUpdate
from app.services.deposit_request_service import DepositRequestService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _locked_request(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED, is_locked=True,
    )
    return accounts, request


async def test_accounts_edit_invoice_numbers_on_locked_request(db_session):
    accounts, request = await _locked_request(db_session)
    svc = DepositRequestService(db_session)
    updated = await svc.update(
        request.id,
        DepositRequestUpdate(sunshine_invoice_number="855/3256/2026-27-CORRECTED"),
        accounts.id, UserRole.ACCOUNTS_TEAM,
    )
    assert updated.sunshine_invoice_number == "855/3256/2026-27-CORRECTED"


async def test_other_fields_stay_locked_for_accounts(db_session):
    accounts, request = await _locked_request(db_session)
    svc = DepositRequestService(db_session)
    with pytest.raises(RecordLockedError):
        await svc.update(
            request.id,
            DepositRequestUpdate(
                sunshine_invoice_number="X-1",
                total_supplier_invoice_amount=Decimal("99999.00"),
            ),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )

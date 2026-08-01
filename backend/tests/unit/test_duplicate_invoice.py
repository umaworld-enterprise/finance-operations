"""Duplicate invoice validation (Aug 2026 batch, item 1.3): no two live
requests may share a Sunshine Invoice No. or Supplier Proforma Invoice No.
Enforced at the service layer (legacy data already holds one duplicate pair,
so DB unique indexes are not an option)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import BusinessRuleError
from app.models.enums import RequestStatus, UserRole
from app.schemas.deposit_request import DepositRequestCreate, DepositRequestUpdate
from app.schemas.tranche import TrancheCreate
from app.services.deposit_request_service import DepositRequestService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _seed(db_session, *, status=RequestStatus.PENDING_PAYMENT):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    existing = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch, status=status
    )
    existing.sunshine_invoice_number = "INV-1001"
    existing.supplier_invoice_number = "SUP-2001"
    await db_session.flush()
    return merch, supplier, customer, existing


def _create_payload(supplier, customer, **extra):
    return DepositRequestCreate(
        supplier_id=supplier.id,
        customer_id=customer.id,
        total_supplier_invoice_amount=Decimal("10000.00"),
        tranches=[TrancheCreate(amount=Decimal("1000.00"), tentative_payment_date=date(2026, 8, 10))],
        **extra,
    )


async def test_duplicate_sunshine_invoice_blocked_case_insensitive(db_session):
    merch, supplier, customer, existing = await _seed(db_session)
    svc = DepositRequestService(db_session)
    with pytest.raises(BusinessRuleError, match=existing.request_number):
        await svc.create(
            _create_payload(supplier, customer, sunshine_invoice_number="  inv-1001 "),
            created_by=merch.id,
        )


async def test_duplicate_supplier_invoice_blocked(db_session):
    merch, supplier, customer, existing = await _seed(db_session)
    svc = DepositRequestService(db_session)
    with pytest.raises(BusinessRuleError, match=existing.request_number):
        await svc.create(
            _create_payload(supplier, customer, supplier_invoice_number="SUP-2001"),
            created_by=merch.id,
        )


async def test_unique_and_empty_numbers_pass(db_session):
    merch, supplier, customer, _ = await _seed(db_session)
    svc = DepositRequestService(db_session)
    created = await svc.create(
        _create_payload(supplier, customer, sunshine_invoice_number="INV-9999"),
        created_by=merch.id,
    )
    assert created.sunshine_invoice_number == "INV-9999"
    # No invoice numbers at all is always fine.
    again = await svc.create(_create_payload(supplier, customer), created_by=merch.id)
    assert again.sunshine_invoice_number is None


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.CANCELLED_BY_MERCHANDISER,
        RequestStatus.CANCELLED_BY_ACCOUNTS,
        RequestStatus.REJECTED_BY_HOM,
    ],
)
async def test_cancelled_and_rejected_requests_do_not_block_reuse(db_session, status):
    merch, supplier, customer, _ = await _seed(db_session, status=status)
    svc = DepositRequestService(db_session)
    created = await svc.create(
        _create_payload(supplier, customer, sunshine_invoice_number="INV-1001"),
        created_by=merch.id,
    )
    assert created.sunshine_invoice_number == "INV-1001"


async def test_update_to_duplicate_number_blocked(db_session):
    merch, supplier, customer, existing = await _seed(db_session)
    other = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch
    )
    svc = DepositRequestService(db_session)
    with pytest.raises(BusinessRuleError, match=existing.request_number):
        await svc.update(
            other.id,
            DepositRequestUpdate(sunshine_invoice_number="INV-1001"),
            merch.id, UserRole.SUPER_ADMIN,
        )


async def test_update_keeping_own_number_is_allowed(db_session):
    merch, _, _, existing = await _seed(db_session)
    svc = DepositRequestService(db_session)
    updated = await svc.update(
        existing.id,
        DepositRequestUpdate(sunshine_invoice_number="INV-1001", remarks="touch"),
        merch.id, UserRole.SUPER_ADMIN,
    )
    assert updated.sunshine_invoice_number == "INV-1001"


async def test_find_invoice_conflict_rejects_unknown_field(db_session):
    svc = DepositRequestService(db_session)
    with pytest.raises(ValueError):
        await svc.find_invoice_conflict("request_number", "Dep-2026-0001")

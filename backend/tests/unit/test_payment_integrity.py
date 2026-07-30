"""Payment integrity per the 14 Jul 2026 change note (C6/C7):

- process_payment must not bulk-pay tranches — it refuses while any tranche
  is unpaid (a tranche only becomes PAID through its TT copy upload).
- process_payment refuses incomplete payment details (the four mandatory
  fields: Payment Date, Bank, Payment Reference Number, Payment Status).
- PaymentCreate requires the four fields; PaymentUpdate stays permissive so
  partial PATCH and the set_ship_date / attach_tt_copy paths keep working.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError
from app.models.enums import PaymentStatus, RequestStatus, TrancheStatus, UserRole
from app.models.payment import PaymentDetails
from app.schemas.payment import PaymentCreate, PaymentUpdate
from app.services.payment_service import PaymentService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

async def _setup(db_session, *, tranche_status=TrancheStatus.UNPAID, complete_payment=True):
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(db_session, supplier=supplier, customer=customer)
    tranche = await make_tranche(
        db_session, request, amount=Decimal("1000.00"), status=tranche_status,
        paid_by=accounts if tranche_status == TrancheStatus.PAID else None,
    )
    payment = PaymentDetails(
        id=uuid.uuid4(),
        deposit_request_id=request.id,
        payment_date=date(2026, 7, 1) if complete_payment else None,
        bank="Test Bank" if complete_payment else None,
        payment_reference_number="REF-123" if complete_payment else None,
        payment_status=PaymentStatus.PROCESSED.value if complete_payment else None,
    )
    db_session.add(payment)
    await db_session.flush()
    return accounts, request, tranche, payment


# ── process_payment: no bulk tranche payment ─────────────────────────────────


@pytest.mark.asyncio
async def test_process_payment_refuses_while_tranches_unpaid(db_session):
    accounts, request, tranche, _ = await _setup(db_session)
    svc = PaymentService(db_session)
    with pytest.raises(ConflictError, match="unpaid tranche"):
        await svc.process_payment(request.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    # The tranche must NOT have been auto-paid on the way to the rejection.
    assert tranche.status == TrancheStatus.UNPAID
    assert request.current_status == RequestStatus.PENDING_PAYMENT
    assert request.is_locked is False


@pytest.mark.asyncio
async def test_process_payment_succeeds_when_all_tranches_paid(db_session):
    accounts, request, _, _ = await _setup(db_session, tranche_status=TrancheStatus.PAID)
    svc = PaymentService(db_session)
    await svc.process_payment(request.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True


# ── process_payment: completeness gate ────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_payment_refuses_incomplete_details(db_session):
    accounts, request, _, _ = await _setup(
        db_session, tranche_status=TrancheStatus.PAID, complete_payment=False
    )
    svc = PaymentService(db_session)
    with pytest.raises(ConflictError, match="incomplete"):
        await svc.process_payment(request.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PENDING_PAYMENT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blank_field", ["payment_date", "bank", "payment_reference_number", "payment_status"]
)
async def test_process_payment_names_each_missing_field(db_session, blank_field):
    accounts, request, _, payment = await _setup(
        db_session, tranche_status=TrancheStatus.PAID
    )
    setattr(payment, blank_field, None)
    await db_session.flush()
    svc = PaymentService(db_session)
    with pytest.raises(ConflictError, match="incomplete"):
        await svc.process_payment(request.id, accounts.id, UserRole.ACCOUNTS_TEAM)


# ── Schemas: PaymentCreate strict, PaymentUpdate permissive ───────────────────


def test_payment_create_requires_the_four_fields():
    with pytest.raises(PydanticValidationError) as exc:
        PaymentCreate()
    missing = {e["loc"][0] for e in exc.value.errors()}
    assert missing == {
        "payment_date",
        "bank",
        "payment_reference_number",
        "payment_status",
    }


def test_payment_create_rejects_blank_strings():
    with pytest.raises(PydanticValidationError):
        PaymentCreate(
            payment_date=date(2026, 7, 1),
            bank="",
            payment_reference_number="REF-1",
            payment_status=PaymentStatus.PROCESSED,
        )


def test_payment_create_accepts_complete_details():
    data = PaymentCreate(
        payment_date=date(2026, 7, 1),
        bank="Test Bank",
        payment_reference_number="REF-1",
        payment_status=PaymentStatus.PROCESSED,
    )
    assert data.accounts_remarks is None  # optional fields remain optional


def test_payment_update_stays_permissive_for_partial_patch():
    data = PaymentUpdate(accounts_remarks="checked with bank")
    assert data.model_dump(exclude_unset=True) == {"accounts_remarks": "checked with bank"}

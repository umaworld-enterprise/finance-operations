"""Yearly Dep-YYYY-0001 request-number generation and uniqueness."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.deposit_request import DepositRequest
from app.repositories.deposit_request_repo import DepositRequestRepository
from tests.factories import make_customer, make_request, make_supplier

pytestmark = pytest.mark.asyncio

YEAR = datetime.now(timezone.utc).year


async def test_first_number_of_year(db_session):
    repo = DepositRequestRepository(db_session)
    number = await repo.generate_request_number()
    assert number == f"Dep-{YEAR}-0001"


async def test_sequence_increments(db_session):
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    repo = DepositRequestRepository(db_session)

    req = await make_request(db_session, supplier=supplier, customer=customer)
    req.request_number = f"Dep-{YEAR}-0007"
    await db_session.flush()

    assert await repo.generate_request_number() == f"Dep-{YEAR}-0008"


async def test_legacy_adt_numbers_ignored(db_session):
    """Historical ADT-YYYY-NNNNN numbers coexist without affecting the new sequence."""
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    repo = DepositRequestRepository(db_session)

    legacy = await make_request(db_session, supplier=supplier, customer=customer)
    legacy.request_number = f"ADT-{YEAR}-00042"
    await db_session.flush()

    assert await repo.generate_request_number() == f"Dep-{YEAR}-0001"


async def test_sequence_survives_4_digit_rollover(db_session):
    """Past 9999 the padded width grows and ordering stays numeric."""
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    repo = DepositRequestRepository(db_session)

    for seq in ("9999", "10000"):
        req = await make_request(db_session, supplier=supplier, customer=customer)
        req.request_number = f"Dep-{YEAR}-{seq}"
        await db_session.flush()

    assert await repo.generate_request_number() == f"Dep-{YEAR}-10001"


async def test_uniqueness_enforced_at_persistence_layer(db_session):
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    first = await make_request(db_session, supplier=supplier, customer=customer)
    dup = DepositRequest(
        id=first.id.__class__(int=first.id.int ^ 1),  # different uuid
        request_number=first.request_number,
        supplier_id=supplier.id,
        customer_id=customer.id,
        deposit_amount=1,
        total_supplier_invoice_amount=1,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.flush()

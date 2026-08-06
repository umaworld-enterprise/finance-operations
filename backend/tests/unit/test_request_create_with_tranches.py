"""DepositRequestService.create — tranche creation and legacy compatibility."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.enums import TrancheStatus
from app.schemas.deposit_request import DepositRequestCreate
from app.schemas.tranche import TrancheCreate
from app.services.deposit_request_service import DepositRequestService
from app.services.tranche_service import TrancheService
from tests.factories import make_customer, make_supplier, make_user

pytestmark = pytest.mark.asyncio

YEAR = datetime.now(timezone.utc).year


async def test_create_with_tranches(db_session):
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    svc = DepositRequestService(db_session)
    request = await svc.create(
        DepositRequestCreate(
            supplier_id=supplier.id,
            customer_id=customer.id,
            total_supplier_invoice_amount=Decimal("10000.00"),
            tranches=[
                TrancheCreate(amount=Decimal("2000.00"), tentative_payment_date=date(2026, 8, 1)),
                TrancheCreate(amount=Decimal("3000.00"), tentative_payment_date=date(2026, 9, 1)),
            ],
        ),
        created_by=merch.id,
    )

    assert request.request_number.startswith(f"Dep-{YEAR}-")
    # deposit_amount = sum of tranches; percentage derived, not user-entered.
    assert Decimal(str(request.deposit_amount)) == Decimal("5000.00")
    assert Decimal(str(request.deposit_percentage)) == Decimal("50.00")

    tranches = await TrancheService(db_session).list_for_request(request.id)
    assert [t.tranche_number for t in tranches] == [1, 2]
    assert [t.label for t in tranches] == ["Deposit - Tranche I", "Deposit - Tranche II"]
    assert all(t.status == TrancheStatus.UNPAID for t in tranches)
    assert all(not t.is_legacy for t in tranches)


async def test_create_without_tranches_gets_compat_tranche(db_session):
    """Legacy API callers (public form) still work — a single compatibility
    tranche covers the full deposit amount."""
    merch = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    svc = DepositRequestService(db_session)
    request = await svc.create(
        DepositRequestCreate(
            supplier_id=supplier.id,
            customer_id=customer.id,
            deposit_amount=Decimal("1500.00"),
            total_supplier_invoice_amount=Decimal("6000.00"),
        ),
        created_by=merch.id,
    )

    tranches = await TrancheService(db_session).list_for_request(request.id)
    assert len(tranches) == 1
    assert tranches[0].is_legacy is True
    assert Decimal(str(tranches[0].amount)) == Decimal("1500.00")
    assert tranches[0].tentative_payment_date is None

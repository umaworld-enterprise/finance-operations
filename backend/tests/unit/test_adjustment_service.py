"""Adjust Invoices: same-supplier validation, available balance, traceability,
immutability of the source paid tranche, and audit entries."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.audit import AuditLog
from app.models.enums import TrancheStatus, UserRole
from app.schemas.tranche import AdjustmentCreate
from app.services.adjustment_service import AdjustmentService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _setup(db_session):
    """Supplier with two requests: request A has a paid tranche (1000),
    request B has an unpaid tranche (destination)."""
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req_a = await make_request(db_session, supplier=supplier, customer=customer)
    req_b = await make_request(db_session, supplier=supplier, customer=customer)
    paid = await make_tranche(
        db_session, req_a, number=1, amount=Decimal("1000.00"), status=TrancheStatus.PAID
    )
    unpaid = await make_tranche(db_session, req_b, number=1, amount=Decimal("800.00"))
    return accounts, supplier, customer, req_a, req_b, paid, unpaid


def _payload(source, destination, amount="300.00", reason=None):
    return AdjustmentCreate(
        source_tranche_id=source.id,
        destination_tranche_id=destination.id,
        amount=Decimal(amount),
        reason=reason,
    )


async def test_create_adjustment_happy_path(db_session):
    accounts, _, _, req_a, req_b, paid, unpaid = await _setup(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, reason="Order cancelled"), accounts.id, UserRole.ACCOUNTS_TEAM
    )
    assert adj.amount == Decimal("300.00")
    assert adj.status.value == "completed"
    # Source paid tranche is preserved untouched — adjustments are additive.
    assert paid.amount == Decimal("1000.00")
    assert paid.status == TrancheStatus.PAID
    # Audit entries exist on the adjustment AND both requests.
    for entity, entity_id in [
        ("invoice_adjustments", adj.id),
        ("deposit_requests", req_a.id),
        ("deposit_requests", req_b.id),
    ]:
        rows = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_name == entity, AuditLog.entity_id == entity_id
            )
        )
        assert rows.scalars().first() is not None, f"missing audit row for {entity}"


async def test_source_must_be_paid(db_session):
    accounts, supplier, customer, _, req_b, _, unpaid = await _setup(db_session)
    other_unpaid = await make_tranche(db_session, req_b, number=2, amount=Decimal("100.00"))
    svc = AdjustmentService(db_session)
    with pytest.raises(ValidationError, match="already-paid"):
        await svc.create(
            _payload(unpaid, other_unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )


async def test_destination_must_be_other_request(db_session):
    accounts, _, _, req_a, _, paid, _ = await _setup(db_session)
    same_request_unpaid = await make_tranche(db_session, req_a, number=2, amount=Decimal("100.00"))
    svc = AdjustmentService(db_session)
    with pytest.raises(ValidationError, match="another invoice"):
        await svc.create(
            _payload(paid, same_request_unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )


async def test_destination_must_be_same_supplier(db_session):
    accounts, _, customer, _, _, paid, _ = await _setup(db_session)
    other_supplier = await make_supplier(db_session)
    other_req = await make_request(db_session, supplier=other_supplier, customer=customer)
    other_tranche = await make_tranche(db_session, other_req, amount=Decimal("100.00"))
    svc = AdjustmentService(db_session)
    with pytest.raises(ValidationError, match="same supplier"):
        await svc.create(
            _payload(paid, other_tranche, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )


async def test_destination_must_be_unpaid(db_session):
    accounts, supplier, customer, _, _, paid, _ = await _setup(db_session)
    req_c = await make_request(db_session, supplier=supplier, customer=customer)
    paid_dest = await make_tranche(
        db_session, req_c, amount=Decimal("100.00"), status=TrancheStatus.PAID
    )
    svc = AdjustmentService(db_session)
    with pytest.raises(ValidationError, match="already paid"):
        await svc.create(_payload(paid, paid_dest, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_balance_cannot_be_exceeded_across_adjustments(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    svc = AdjustmentService(db_session)
    await svc.create(_payload(paid, unpaid, "700.00"), accounts.id, UserRole.ACCOUNTS_TEAM)
    # 700 already reallocated of 1000 — only 300 remains.
    with pytest.raises(ValidationError, match="available paid balance"):
        await svc.create(_payload(paid, unpaid, "400.00"), accounts.id, UserRole.ACCOUNTS_TEAM)
    # Exactly the remaining balance is fine.
    adj = await svc.create(_payload(paid, unpaid, "300.00"), accounts.id, UserRole.ACCOUNTS_TEAM)
    assert adj.amount == Decimal("300.00")


async def test_merchandiser_cannot_adjust(db_session):
    _, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    svc = AdjustmentService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.create(_payload(paid, unpaid), merch.id, UserRole.MERCHANDISER)


async def test_traceable_from_both_requests(db_session):
    accounts, _, _, req_a, req_b, paid, unpaid = await _setup(db_session)
    svc = AdjustmentService(db_session)
    await svc.create(_payload(paid, unpaid, "250.00"), accounts.id, UserRole.ACCOUNTS_TEAM)

    from_source = await svc.list_for_request(req_a.id)
    from_destination = await svc.list_for_request(req_b.id)
    assert len(from_source) == 1
    assert len(from_destination) == 1
    assert from_source[0].id == from_destination[0].id
    assert from_source[0].source_request_number == req_a.request_number
    assert from_source[0].destination_request_number == req_b.request_number


async def test_supplier_options_report_remaining_balance(db_session):
    accounts, supplier, _, _, _, paid, unpaid = await _setup(db_session)
    svc = AdjustmentService(db_session)
    await svc.create(_payload(paid, unpaid, "600.00"), accounts.id, UserRole.ACCOUNTS_TEAM)

    sources, destinations = await svc.supplier_tranche_options(supplier.id)
    assert len(sources) == 1
    assert sources[0].available_paid_balance == Decimal("400.00")
    assert sources[0].adjusted_out_total == Decimal("600.00")
    assert len(destinations) == 1
    assert destinations[0].adjusted_in_total == Decimal("600.00")

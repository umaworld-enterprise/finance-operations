"""Adjust Invoices: same-supplier validation, available balance, traceability,
immutability of the source paid tranche, audit entries, and the shipped-request
exclusion (change note B1)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    ValidationError,
)
from app.models.audit import AuditLog
from app.models.enums import AdjustmentStatus, TrancheStatus, UserRole
from app.models.payment import PaymentDetails
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
    with pytest.raises(ValidationError, match="not payable"):
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


async def test_non_requester_roles_cannot_adjust(db_session):
    _, _, _, _, _, paid, unpaid = await _setup(db_session)
    hom = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    svc = AdjustmentService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.create(_payload(paid, unpaid), hom.id, UserRole.HEAD_OF_MERCHANDISER)
    finance = await make_user(db_session, UserRole.FINANCE_ADMIN)
    with pytest.raises(AuthorizationError):
        await svc.create(_payload(paid, unpaid), finance.id, UserRole.FINANCE_ADMIN)


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


# ── B1: shipped requests are excluded from Adjust Invoice ─────────────────────


async def _add_payment_details(db_session, request, *, ship_date=None):
    db_session.add(
        PaymentDetails(
            id=uuid.uuid4(),
            deposit_request_id=request.id,
            ship_date=ship_date,
        )
    )
    await db_session.flush()


async def test_shipped_request_appears_in_neither_option_list(db_session):
    accounts, supplier, customer, req_a, req_b, paid, unpaid = await _setup(db_session)
    # req_a also gets an unpaid tranche so it would normally feed BOTH lists.
    await make_tranche(db_session, req_a, number=2, amount=Decimal("200.00"))
    await _add_payment_details(db_session, req_a, ship_date=date(2026, 7, 20))

    svc = AdjustmentService(db_session)
    sources, destinations = await svc.supplier_tranche_options(supplier.id)

    listed_ids = {t.id for t in sources} | {t.id for t in destinations}
    assert paid.id not in listed_ids
    assert all(t.request_number != req_a.request_number for t in sources + destinations)
    # req_b (unshipped) is unaffected.
    assert {t.id for t in destinations} == {unpaid.id}


async def test_unshipped_payment_details_row_does_not_exclude(db_session):
    """A partial payment_details row with NULL ship_date must not filter the
    request out (the outer join keeps rows without payment_details too)."""
    accounts, supplier, _, req_a, _, paid, unpaid = await _setup(db_session)
    await _add_payment_details(db_session, req_a, ship_date=None)

    svc = AdjustmentService(db_session)
    sources, destinations = await svc.supplier_tranche_options(supplier.id)
    assert {t.id for t in sources} == {paid.id}
    assert {t.id for t in destinations} == {unpaid.id}


async def test_create_rejects_shipped_source_request(db_session):
    accounts, _, _, req_a, _, paid, unpaid = await _setup(db_session)
    await _add_payment_details(db_session, req_a, ship_date=date(2026, 7, 20))
    svc = AdjustmentService(db_session)
    with pytest.raises(BusinessRuleError, match=req_a.request_number):
        await svc.create(_payload(paid, unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_create_rejects_shipped_destination_request(db_session):
    accounts, _, _, _, req_b, paid, unpaid = await _setup(db_session)
    await _add_payment_details(db_session, req_b, ship_date=date(2026, 7, 21))
    svc = AdjustmentService(db_session)
    with pytest.raises(BusinessRuleError, match=req_b.request_number):
        await svc.create(_payload(paid, unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)


# ── B3: merchandiser-raised requests + Accounts approval queue ────────────────


async def _merch(db_session):
    return await make_user(db_session, UserRole.MERCHANDISER)


async def test_merchandiser_create_requires_reason(db_session):
    _, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    with pytest.raises(ValidationError, match="reason is mandatory"):
        await svc.create(_payload(paid, unpaid, "50.00"), merch.id, UserRole.MERCHANDISER)
    with pytest.raises(ValidationError, match="reason is mandatory"):
        await svc.create(
            _payload(paid, unpaid, "50.00", reason="   "), merch.id, UserRole.MERCHANDISER
        )


async def test_merchandiser_create_is_pending_approval(db_session):
    _, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "300.00", reason="Order cancelled"),
        merch.id, UserRole.MERCHANDISER,
    )
    assert adj.status == AdjustmentStatus.PENDING_APPROVAL
    assert adj.performed_by == merch.id


async def test_pending_does_not_consume_balance(db_session):
    accounts, supplier, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    await svc.create(
        _payload(paid, unpaid, "700.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    # Option lists still report the FULL paid balance available.
    sources, _ = await svc.supplier_tranche_options(supplier.id)
    assert sources[0].available_paid_balance == Decimal("1000.00")
    # Accounts can still complete an adjustment using the full balance.
    adj = await svc.create(
        _payload(paid, unpaid, "1000.00"), accounts.id, UserRole.ACCOUNTS_TEAM
    )
    assert adj.status == AdjustmentStatus.COMPLETED


async def test_double_spend_across_two_pending_requests(db_session):
    """Two pending requests may together exceed the balance — approval is the
    enforcement point, so the second approval must fail."""
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    first = await svc.create(
        _payload(paid, unpaid, "700.00", reason="r1"), merch.id, UserRole.MERCHANDISER
    )
    second = await svc.create(
        _payload(paid, unpaid, "700.00", reason="r2"), merch.id, UserRole.MERCHANDISER
    )
    approved = await svc.approve(first.id, accounts.id, UserRole.ACCOUNTS_TEAM, "ok")
    assert approved.status == AdjustmentStatus.COMPLETED
    # 700 of 1000 now consumed — the second 700 no longer fits.
    with pytest.raises(ValidationError, match="available paid balance"):
        await svc.approve(second.id, accounts.id, UserRole.ACCOUNTS_TEAM, "ok")


async def test_approve_writes_audit_on_adjustment_and_both_requests(db_session):
    accounts, _, _, req_a, req_b, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "200.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    await svc.approve(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "verified with bank")

    status_rows = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_name == "invoice_adjustments",
            AuditLog.entity_id == adj.id,
            AuditLog.field_name == "status",
        )
    )
    row = status_rows.scalars().one()
    assert "verified with bank" in row.new_value
    for req in (req_a, req_b):
        rows = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_name == "deposit_requests",
                AuditLog.entity_id == req.id,
                AuditLog.field_name == "invoice_adjustment_approved",
            )
        )
        assert rows.scalars().first() is not None


async def test_reject_sets_rejected_and_never_consumes_balance(db_session):
    accounts, supplier, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "700.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    rejected = await svc.reject(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "not justified")
    assert rejected.status == AdjustmentStatus.REJECTED
    sources, _ = await svc.supplier_tranche_options(supplier.id)
    assert sources[0].available_paid_balance == Decimal("1000.00")
    # A decided adjustment cannot be decided again.
    with pytest.raises(ConflictError, match="pending"):
        await svc.approve(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "changed my mind")


async def test_approve_reasserts_ship_date_exclusion(db_session):
    """State may change between raise and decision — a request that shipped in
    the meantime blocks approval."""
    accounts, _, _, req_a, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    await _add_payment_details(db_session, req_a, ship_date=date(2026, 7, 25))
    with pytest.raises(BusinessRuleError, match=req_a.request_number):
        await svc.approve(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "ok")


async def test_approve_rejects_destination_paid_meanwhile(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    unpaid.status = TrancheStatus.PAID
    await db_session.flush()
    with pytest.raises(ValidationError, match="not payable"):
        await svc.approve(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "ok")


async def test_only_deciders_can_approve_or_reject(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    with pytest.raises(AuthorizationError):
        await svc.approve(adj.id, merch.id, UserRole.MERCHANDISER, "self-approve")
    with pytest.raises(AuthorizationError):
        await svc.reject(adj.id, merch.id, UserRole.MERCHANDISER, "self-reject")


async def test_pending_queue_lists_oldest_first(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    a1 = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r1"), merch.id, UserRole.MERCHANDISER
    )
    a2 = await svc.create(
        _payload(paid, unpaid, "200.00", reason="r2"), merch.id, UserRole.MERCHANDISER
    )
    completed = await svc.create(_payload(paid, unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)
    # CURRENT_TIMESTAMP has second precision on SQLite — same-second inserts
    # tie. Pin distinct timestamps so ordering is deterministic.
    from datetime import datetime, timezone

    a1.created_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    a2.created_at = datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)
    await db_session.flush()

    pending = await svc.list_pending()
    assert [p.id for p in pending] == [a1.id, a2.id]
    assert completed.id not in {p.id for p in pending}


async def test_rejected_tranche_is_never_an_adjustment_destination(db_session):
    """Aug 2026 rejection workflow: a rejected tranche is a dead record —
    excluded from the destination options and refused at create/approve."""
    accounts, supplier, _, _, _, paid, unpaid = await _setup(db_session)
    unpaid.status = TrancheStatus.REJECTED
    await db_session.flush()
    svc = AdjustmentService(db_session)

    _, destinations = await svc.supplier_tranche_options(supplier.id)
    assert unpaid.id not in {t.id for t in destinations}

    with pytest.raises(ValidationError, match="not payable"):
        await svc.create(_payload(paid, unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_approve_rejects_destination_rejected_meanwhile(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    unpaid.status = TrancheStatus.REJECTED
    await db_session.flush()
    with pytest.raises(ValidationError, match="not payable"):
        await svc.approve(adj.id, accounts.id, UserRole.ACCOUNTS_TEAM, "ok")


async def test_merchandiser_history_scoped_to_own(db_session):
    accounts, _, _, _, _, paid, unpaid = await _setup(db_session)
    merch = await _merch(db_session)
    svc = AdjustmentService(db_session)
    mine = await svc.create(
        _payload(paid, unpaid, "100.00", reason="r"), merch.id, UserRole.MERCHANDISER
    )
    await svc.create(_payload(paid, unpaid, "50.00"), accounts.id, UserRole.ACCOUNTS_TEAM)
    own = await svc.list_recent(performed_by=merch.id)
    assert {a.id for a in own} == {mine.id}

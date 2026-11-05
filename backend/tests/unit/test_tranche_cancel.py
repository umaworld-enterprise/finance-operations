"""Merchandiser cancels a tranche (5 Nov 2026).

Delete removes the row and is refused once Accounts have touched it; cancel
keeps the row visible with a reason, works regardless, and takes the amount
out of the deposit total so replacements can be added.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.models.enums import RequestStatus, TrancheStatus, UserRole
from app.services.tranche_service import TrancheService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _setup(db_session, amounts=("600.00", "400.00")):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT, deposit_amount=Decimal("1000.00"),
    )
    tranches = [
        await make_tranche(db_session, req, number=i + 1, amount=Decimal(a))
        for i, a in enumerate(amounts)
    ]
    return merch, accounts, req, tranches


async def test_cancel_keeps_the_row_and_records_the_reason(db_session):
    merch, _accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)

    cancelled = await svc.cancel_tranche(
        req.id, t1.id, "Supplier withdrew the shipment", merch.id, UserRole.MERCHANDISER,
    )
    assert cancelled.status == TrancheStatus.CANCELLED
    assert cancelled.rejection_reason == "Supplier withdrew the shipment"
    # The row survives — this is the difference from delete.
    assert len(await svc.list_for_request(req.id)) == 2


async def test_cancelled_value_leaves_the_deposit_total(db_session):
    merch, _accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    await svc.cancel_tranche(req.id, t1.id, "no longer needed", merch.id, UserRole.MERCHANDISER)
    await db_session.refresh(req)
    assert Decimal(str(req.deposit_amount)) == Decimal("400.00")


async def test_reason_is_mandatory(db_session):
    merch, _accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ValidationError, match="reason is mandatory"):
        await svc.cancel_tranche(req.id, t1.id, "   ", merch.id, UserRole.MERCHANDISER)


async def test_cancel_works_even_after_accounts_touch_the_tranche(db_session):
    """The point of cancel: delete is refused here, cancel is not."""
    merch, accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    await svc.attach_tt_copy(
        req.id, t1.id, tt_copy_url="https://drive.test/x", tt_copy_file_id="f1",
        tt_copy_filename="tt.pdf", user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
    )
    with pytest.raises(ConflictError):
        await svc.delete_tranche(req.id, t1.id, merch.id, UserRole.MERCHANDISER)

    cancelled = await svc.cancel_tranche(
        req.id, t1.id, "order pulled", merch.id, UserRole.MERCHANDISER,
    )
    assert cancelled.status == TrancheStatus.CANCELLED


async def test_the_last_tranche_may_be_cancelled(db_session):
    """Delete refuses to leave a request with no tranches; cancel keeps the
    row, so the rule does not apply."""
    merch, _accounts, req, (only,) = await _setup(db_session, amounts=("1000.00",))
    svc = TrancheService(db_session)
    with pytest.raises(ValidationError):
        await svc.delete_tranche(req.id, only.id, merch.id, UserRole.MERCHANDISER)

    cancelled = await svc.cancel_tranche(req.id, only.id, "duplicate file", merch.id, UserRole.MERCHANDISER)
    assert cancelled.status == TrancheStatus.CANCELLED


async def test_paid_tranche_cannot_be_cancelled(db_session):
    merch, accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    t1.status = TrancheStatus.PAID
    await db_session.flush()
    with pytest.raises(ConflictError, match="already paid"):
        await svc.cancel_tranche(req.id, t1.id, "oops", merch.id, UserRole.MERCHANDISER)


async def test_accounts_cannot_cancel_only_merchandisers(db_session):
    _merch, accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.cancel_tranche(req.id, t1.id, "nope", accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_cancelling_twice_conflicts(db_session):
    merch, _accounts, req, (t1, _t2) = await _setup(db_session)
    svc = TrancheService(db_session)
    await svc.cancel_tranche(req.id, t1.id, "first", merch.id, UserRole.MERCHANDISER)
    with pytest.raises(ConflictError, match="already cancelled"):
        await svc.cancel_tranche(req.id, t1.id, "again", merch.id, UserRole.MERCHANDISER)

"""While a merchandiser has their request on hold (or has cancelled it),
Accounts must not be able to act on it in any way (UAT change note Aug 2026,
item 7) — plus the last-status-actor lookup that names WHO acted (item 6)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError
from app.models.enums import RequestStatus, TrancheStatus, UserRole
from app.schemas.tranche import TranchePaymentDetailsUpdate
from app.services.deposit_request_service import DepositRequestService
from app.services.tranche_service import TrancheService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio

_HELD = RequestStatus.HOLD_BY_MERCHANDISER


async def _setup(db_session, status=_HELD):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=status,
    )
    tranche = await make_tranche(db_session, request, status=TrancheStatus.UNPAID)
    return merch, accounts, request, tranche


async def test_accounts_cannot_record_payment_details_while_held(db_session):
    _, accounts, request, tranche = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="on hold by the merchandiser"):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(payment_date=date(2026, 8, 10), bank="DBS (USD)"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )


async def test_accounts_cannot_attach_tt_copy_while_held_or_closed(db_session):
    _, accounts, request, tranche = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="on hold by the merchandiser"):
        await svc.attach_tt_copy(
            request.id, tranche.id,
            tt_copy_url="https://drive.example/tt", tt_copy_file_id="f1",
            tt_copy_filename="tt.pdf",
            user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
        )
    # Terminal statuses block the attach too (previously unguarded).
    _, accounts2, cancelled, tranche2 = await _setup(
        db_session, status=RequestStatus.CANCELLED_BY_MERCHANDISER
    )
    with pytest.raises(ConflictError, match="cancelled or rejected"):
        await svc.attach_tt_copy(
            cancelled.id, tranche2.id,
            tt_copy_url="https://drive.example/tt2", tt_copy_file_id="f2",
            tt_copy_filename="tt2.pdf",
            user_id=accounts2.id, role=UserRole.ACCOUNTS_TEAM,
        )


async def test_accounts_cannot_reject_tranche_while_held(db_session):
    _, accounts, request, tranche = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="on hold by the merchandiser"):
        await svc.reject_tranche(
            request.id, tranche.id, "wrong amount",
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )


async def test_accounts_cannot_pay_tranche_while_held(db_session):
    """The status guard fires before the readiness gate, so a held request
    fails with 'held', not a misleading missing-TT message."""
    _, accounts, request, tranche = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="on hold by the merchandiser"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_last_status_actor_names_the_holder(db_session):
    """Item 6: the queue shows WHO held/cancelled — resolved from the most
    recent status-history row."""
    merch, accounts, request, _ = await _setup(
        db_session, status=RequestStatus.PENDING_PAYMENT
    )
    svc = DepositRequestService(db_session)
    await svc.transition_status(
        request.id, RequestStatus.HOLD_BY_MERCHANDISER,
        merch.id, UserRole.MERCHANDISER, "supplier renegotiating",
    )
    actors = await svc.get_last_status_actors([request.id])
    assert actors[request.id] == merch.full_name

    # A later transition by the other side replaces the name.
    await svc.transition_status(
        request.id, RequestStatus.PENDING_PAYMENT, merch.id, UserRole.MERCHANDISER
    )
    await svc.transition_status(
        request.id, RequestStatus.HOLD_BY_ACCOUNTS, accounts.id, UserRole.ACCOUNTS_TEAM
    )
    actors = await svc.get_last_status_actors([request.id])
    assert actors[request.id] == accounts.full_name

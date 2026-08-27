"""Request-level rejection by Accounts (UAT change note Aug 2026, items
12/17/18): terminal status, mandatory-reason transition, full merchandiser
edit-lock, invoice-number reuse, and the merchandiser + HoM notification."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    InvalidStatusTransitionError,
)
from app.domain.rules.status_transitions import assert_transition_allowed
from app.models.deposit_request import DepositRequest
from app.models.enums import AccountsActionType, RequestStatus, UserRole
from app.models.masters import Customer, Supplier, User
from app.models.notification import Notification
from app.models.workflow import AccountsAction, StatusHistory
from app.schemas.deposit_request import DepositRequestUpdate
from app.schemas.tranche import TrancheCreate
from app.services.deposit_request_service import DepositRequestService
from app.services.notification_service import (
    TYPE_REQUEST_REJECTED,
    notify_request_rejected_by_accounts,
)
from app.services.tranche_service import TrancheService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    """The notification test commits (own-session entry point) — wipe."""
    yield
    for model in (
        Notification, StatusHistory, AccountsAction,
        DepositRequest, User, Supplier, Customer,
    ):
        await db_session.execute(delete(model))
    await db_session.commit()


async def _setup(db_session, status=RequestStatus.PENDING_PAYMENT):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=status,
    )
    return merch, accounts, request


# ── Transition rules ──────────────────────────────────────────────────────────


async def test_transition_rules():
    # Accounts (and Super Admin) may reject from pending or accounts-hold.
    for src in (RequestStatus.PENDING_PAYMENT, RequestStatus.HOLD_BY_ACCOUNTS):
        for role in (UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN):
            assert_transition_allowed(src, RequestStatus.REJECTED_BY_ACCOUNTS, role)
    # A merchandiser can never reject.
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(
            RequestStatus.PENDING_PAYMENT,
            RequestStatus.REJECTED_BY_ACCOUNTS,
            UserRole.MERCHANDISER,
        )
    # Terminal: nothing leads out of rejected_by_accounts.
    for target in RequestStatus:
        if target == RequestStatus.REJECTED_BY_ACCOUNTS:
            continue
        with pytest.raises(InvalidStatusTransitionError):
            assert_transition_allowed(
                RequestStatus.REJECTED_BY_ACCOUNTS, target, UserRole.SUPER_ADMIN
            )


# ── Service flow ──────────────────────────────────────────────────────────────


async def test_reject_writes_history_and_accounts_action(db_session):
    _, accounts, request = await _setup(db_session)
    svc = DepositRequestService(db_session)
    rejected = await svc.transition_status(
        request.id, RequestStatus.REJECTED_BY_ACCOUNTS,
        accounts.id, UserRole.ACCOUNTS_TEAM, "Supplier failed verification.",
    )
    assert rejected.current_status == RequestStatus.REJECTED_BY_ACCOUNTS

    history = (
        await db_session.execute(
            select(StatusHistory).where(StatusHistory.deposit_request_id == request.id)
        )
    ).scalars().all()
    assert any(
        h.new_status == RequestStatus.REJECTED_BY_ACCOUNTS
        and h.remarks == "Supplier failed verification."
        for h in history
    )
    actions = (
        await db_session.execute(
            select(AccountsAction).where(AccountsAction.deposit_request_id == request.id)
        )
    ).scalars().all()
    assert [a.action_type for a in actions] == [AccountsActionType.REJECT]


# ── Item 17: invoice numbers become reusable ─────────────────────────────────


async def test_rejected_request_frees_its_invoice_numbers(db_session):
    _, accounts, request = await _setup(db_session)
    request.sunshine_invoice_number = "AGV-9001"
    request.supplier_invoice_number = "PF-9001"
    await db_session.flush()
    svc = DepositRequestService(db_session)

    # Live request blocks reuse…
    assert await svc.find_invoice_conflict("sunshine_invoice_number", "AGV-9001") is not None

    await svc.transition_status(
        request.id, RequestStatus.REJECTED_BY_ACCOUNTS,
        accounts.id, UserRole.ACCOUNTS_TEAM, "Wrong file.",
    )
    # …a rejected one does not (either field).
    assert await svc.find_invoice_conflict("sunshine_invoice_number", "AGV-9001") is None
    assert await svc.find_invoice_conflict("supplier_invoice_number", "PF-9001") is None


# ── Item 18: merchandiser edit-lock ──────────────────────────────────────────


async def test_merchandiser_cannot_edit_anything_after_rejection(db_session):
    merch, accounts, request = await _setup(db_session)
    svc = DepositRequestService(db_session)
    await svc.transition_status(
        request.id, RequestStatus.REJECTED_BY_ACCOUNTS,
        accounts.id, UserRole.ACCOUNTS_TEAM, "Duplicate order.",
    )

    with pytest.raises(BusinessRuleError, match="no longer be edited"):
        await svc.update(
            request.id, DepositRequestUpdate(estimated_etd=date(2026, 12, 1)),
            merch.id, UserRole.MERCHANDISER,
        )
    with pytest.raises(BusinessRuleError, match="no longer be edited"):
        await svc.update_remarks(request.id, merch.id, UserRole.MERCHANDISER, "note")
    with pytest.raises(ConflictError, match="cancelled or rejected"):
        await TrancheService(db_session).add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_hold_and_resume_are_impossible_after_rejection(db_session):
    merch, accounts, request = await _setup(db_session)
    svc = DepositRequestService(db_session)
    await svc.transition_status(
        request.id, RequestStatus.REJECTED_BY_ACCOUNTS,
        accounts.id, UserRole.ACCOUNTS_TEAM, "Closed.",
    )
    for target, role, user in (
        (RequestStatus.HOLD_BY_MERCHANDISER, UserRole.MERCHANDISER, merch),
        (RequestStatus.PENDING_PAYMENT, UserRole.ACCOUNTS_TEAM, accounts),
        (RequestStatus.REOPENED, UserRole.ACCOUNTS_TEAM, accounts),
    ):
        with pytest.raises(InvalidStatusTransitionError):
            await svc.transition_status(request.id, target, user.id, role)


# ── Item 12: merchandiser AND HoM are notified ───────────────────────────────


def _patch_factory(engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)


async def test_rejection_notifies_merchandiser_and_all_homs(db_session, engine, monkeypatch):
    merch, accounts, request = await _setup(db_session)
    hom1 = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    hom2 = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_request_rejected_by_accounts(request.id, "Budget exceeded.")

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_REQUEST_REJECTED)
        )
    ).scalars().all()
    assert {n.user_id for n in rows} == {merch.id, hom1.id, hom2.id}
    by_user = {n.user_id: n for n in rows}
    # Everyone gets the reason; each audience's link opens their own view.
    for n in rows:
        assert "Budget exceeded." in n.body
        assert request.request_number in n.body
    assert by_user[merch.id].url == f"/merchandiser/{request.id}"
    assert by_user[hom1.id].url == f"/hom/{request.id}"
    assert by_user[hom2.id].url == f"/hom/{request.id}"

# ── Tranche-derived guards on whole-request transitions (19 Aug 2026) ─────────


async def test_paid_tranche_blocks_request_hold_and_reject(db_session):
    """Once ANY tranche is paid, whole-request Hold and Reject are refused —
    money already left, so those transitions would record wrong information."""
    from app.models.enums import TrancheStatus
    from tests.factories import make_tranche

    merch, accounts, request = await _setup(db_session)
    t1 = await make_tranche(db_session, request, number=1, amount=Decimal("400.00"))
    await make_tranche(db_session, request, number=2, amount=Decimal("600.00"))
    t1.status = TrancheStatus.PAID
    await db_session.flush()
    svc = DepositRequestService(db_session)
    with pytest.raises(BusinessRuleError, match="already been paid"):
        await svc.transition_status(
            request.id, RequestStatus.HOLD_BY_ACCOUNTS, accounts.id, UserRole.ACCOUNTS_TEAM
        )
    with pytest.raises(BusinessRuleError, match="already been paid"):
        await svc.transition_status(
            request.id, RequestStatus.REJECTED_BY_ACCOUNTS, accounts.id,
            UserRole.ACCOUNTS_TEAM, remarks="wrong",
        )


async def test_cancel_blocked_until_unpaid_tranches_deleted(db_session):
    """Rejected tranche + unpaid tranche: the merchandiser must delete the
    unpaid tranche(s) explicitly before the file can be closed — nothing is
    closed silently (19 Aug 2026)."""
    from app.models.enums import TrancheStatus
    from tests.factories import make_tranche

    merch, _, request = await _setup(db_session)
    t1 = await make_tranche(db_session, request, number=1, amount=Decimal("400.00"))
    t2 = await make_tranche(db_session, request, number=2, amount=Decimal("600.00"))
    t1.status = TrancheStatus.REJECTED
    await db_session.flush()
    svc = DepositRequestService(db_session)
    with pytest.raises(BusinessRuleError, match="Delete the unpaid"):
        await svc.transition_status(
            request.id, RequestStatus.CANCELLED_BY_MERCHANDISER, merch.id, UserRole.MERCHANDISER
        )
    # Delete the unpaid tranche — then the file closes normally.
    await TrancheService(db_session).delete_tranche(
        request.id, t2.id, merch.id, UserRole.MERCHANDISER
    )
    updated = await svc.transition_status(
        request.id, RequestStatus.CANCELLED_BY_MERCHANDISER, merch.id, UserRole.MERCHANDISER
    )
    assert updated.current_status == RequestStatus.CANCELLED_BY_MERCHANDISER
